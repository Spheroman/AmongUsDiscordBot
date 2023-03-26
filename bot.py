import random
from dotenv import load_dotenv
import discord
from discord.ext import commands
import os
import json
from rembg.bg import remove
from PIL import Image
import time

load_dotenv()
token = os.getenv('TOKEN')
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

players = {}
crewmates = []
impostors = []
game_started = False
last_meeting = 0
sabotage = None
meetings = 2
votes = {}
announcements = discord.utils.get(bot.get_all_channels(), name="game-announcements")


class Embed(discord.Embed):
    def __init__(self, title, description, color):
        super().__init__(title=title, description=description, color=color)
        self.taskidx = 0
        self.set_footer(text="Among Us Bot")

    def add_field(self, name, value, inline=False):
        super().add_field(name=name, value=value, inline=inline)

    def set_footer(self, text):
        super().set_footer(text=text)

    def set_tasks(self, title, tasks):
        if self.taskidx == 0:
            self.taskidx = len(self.fields)
            self.add_field(title, tasks, inline=False)
        else:
            self.set_field_at(self.taskidx, name=title, value=tasks, inline=False)


class Task:
    def __init__(self, task_dict):
        self.name = task_dict["name"]
        self.location = task_dict["location"]
        self.id = task_dict["id"]
        self.task_type = task_dict["type"]

    def __str__(self):
        return f"{self.name} in {self.location}"


taskjson = json.load(open("tasks.json"))
tasks = []
for task in taskjson:
    tasks.append(Task(task))


class Player:
    def __init__(self, member: discord.Member, channel):
        self.member = member
        self.role = None
        self.alive = True
        self.tasks = []
        self.channel = channel
        self.embed = Embed("Welcome to the game!", "Please wait for people to join.", discord.Color.red())
        self.embedmsg = None
        self.image = None
        self.meetings = meetings

    def __str__(self):
        return self.member.name

    async def create_channel(self):
        overwrites = {
            self.member.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            discord.utils.get(self.member.guild.roles, name="Moderator"): discord.PermissionOverwrite(
                read_messages=True),
            self.member.guild.me: discord.PermissionOverwrite(read_messages=True),
            self.member: discord.PermissionOverwrite(read_messages=True)
        }
        category = discord.utils.get(self.member.guild.categories, name="Game Channels")
        channel_name = f"{self.member.name.lower()}-private"
        self.channel = await self.member.guild.create_text_channel(channel_name, overwrites=overwrites,
                                                                   category=category)

    def add_task(self, task):
        self.tasks.append(task)

    async def set_role(self, role):
        if role == "Impostor":
            self.embed = Embed("You are an Impostor!",
                               "Your job is to kill all the Crewmates before they complete all of their tasks.",
                               discord.Color.red())
            self.embed.add_field("Kill", "To kill a Crewmate, use the command `!kill <player>`", inline=True)
            self.embed.add_field("Sabotage", "To sabotage, use the command `!sabotage`", inline=True)
            self.embed.set_footer("This message will update throughout the game.")
            self.embedmsg = await self.channel.send(embed=self.embed)
            impostor = Impostor(self)
            impostors.append(self.member.id)
            players[self.member.id] = impostor
        elif role == "Crewmate":
            self.embed = Embed("You are a Crewmate!",
                               "Your job is to complete all tasks before the Impostors kill everyone.",
                               discord.Color.blue())
            self.embedmsg = await self.channel.send(embed=self.embed)
            crewmate = Crewmate(self)
            crewmates.append(self.member.id)
            players[self.member.id] = crewmate
        else:
            raise ValueError("Invalid role")

    def set_alive(self, alive):
        self.alive = alive

    async def update_embed(self):
        pass


class Impostor(Player):
    def __init__(self, player):
        super().__init__(player.member, player.channel)
        self.embedmsg = player.embedmsg
        self.embed = player.embed
        self.role = "Impostor"
        self.image = player.image
        banner_gen(self)

    async def update_embed(self):
        taskstrings = []
        for task in self.tasks:
            taskstrings.append(str(task))
        self.embed.set_tasks("Fake Tasks", "\n".join(taskstrings))
        await self.embedmsg.edit(embed=self.embed)

    def kill(self, target):
        # logic for killing a crewmate
        pass


class Crewmate(Player):
    def __init__(self, player):
        super().__init__(player.member, player.channel)
        self.embedmsg = player.embedmsg
        self.role = "Crewmate"
        self.embed = player.embed
        self.image = player.image
        banner_gen(self)

    async def update_embed(self):
        taskstrings = []
        for task in self.tasks:
            taskstrings.append(str(task))
        self.embed.set_tasks("Tasks", "\n".join(taskstrings))
        await self.embedmsg.edit(embed=self.embed)

    async def finish_task(self, task):
        self.tasks.remove(task)
        await self.channel.send(f"Task {task} completed!")


@bot.command()
async def join(ctx):
    # Create player object and store in dictionary
    player = Player(ctx.author, None)
    await player.create_channel()
    await player.member.add_roles(discord.utils.get(ctx.guild.roles, name="Player"))
    player.embedmsg = await player.channel.send(embed=player.embed)
    players[ctx.author.id] = player

    await ctx.send(f"{ctx.author.mention} has joined the game.")
    if ctx.message.attachments:
        await picture(ctx)


@bot.command()
async def meeting(ctx):
    if ctx.author.id not in players:
        await ctx.send("You are not in the game.")
        return
    if ctx.channel.name != players[ctx.author.id].channel.name:
        await ctx.delete()
        players[ctx.author.id].channel.send("You can only call an emergency meeting in your channel.")
        return
    if players[ctx.author.id].meetings == 0:
        await ctx.send("You have no meetings left.")
        return
    await announcements.send(f"{ctx.author.mention} has called an emergency meeting. Please go to the meeting area.")
    players[ctx.author.id].meetings -= 1


@bot.command()
async def vote(ctx, member: discord.Member):
    if ctx.author.id not in players:
        await ctx.send("You are not in the game.")
        return
    if ctx.channel.name != players[ctx.author.id].channel.name:
        await ctx.delete()
        players[ctx.author.id].channel.send("You can only vote in your channel.")
        return
    if member.id not in players:
        await ctx.send("That player is not in the game.")
        return
    if not players[member.id].alive:
        await ctx.send("That player is dead.")
        return
    votes[ctx.author.id] = member.id
    await ctx.send(f" have voted for {member.name}.")
    await announcements.send(f"{ctx.author.name} has voted.")
    if len(votes) == len([value for value in players.values() if value.alive]):
        await end_meeting(ctx)


@bot.command()
async def end_meeting(ctx):
    if ctx.author.id not in players:
        await ctx.send("You are not in the game.")
        return
    await announcements.send("The meeting has ended.")
    await announcements.send(
        f"Voting results:\n{'/n'.join([f'{players[key].member.name}: {players[value].member.name}' for key, value in votes.items()])}")
    await announcements.send(vote_results())


def vote_results():
    results = {}
    for vote in votes.values():
        if vote in results:
            results[vote] += 1
        else:
            results[vote] = 1
    results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    if len(results) > 1 and results[0][1] == results[1][1]:
        return "Tie! Nobody is voted out."
    else:
        players[results[0][0]].alive = False
        return f"{players[results[0][0]].member.name} was voted out."


async def assign_tasks():
    # Assign tasks to players
    num_tasks = len(tasks)
    num_players = len(players)
    tasks_per_player = num_tasks // num_players
    tasks_per_player += 1

    all_players = list(players.values())
    random.shuffle(all_players)

    for i in range(num_tasks):
        all_players[i % num_players].add_task(tasks[i])

    # Send tasks to players
    for player in all_players:
        await player.update_embed()


@bot.command()
async def leave(ctx):
    # Check if player is in game
    if ctx.author.id not in players:
        await ctx.send("You are not in the game.")
        return

    # Remove player from game
    player = players[ctx.author.id]
    await player.channel.delete()
    await player.member.remove_roles(discord.utils.get(ctx.guild.roles, name="Player"))
    del players[ctx.author.id]

    await ctx.send(f"{ctx.author.mention} has left the game.")


@bot.command()
async def picture(ctx):
    # Check if player is in game
    if ctx.author.id not in players:
        await ctx.send("You are not in the game.")
        return

    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if attachment.content_type.startswith("image"):
            path = f"players/{ctx.author.name}.png"
            await attachment.save(path)
            img = Image.open(path)
            img = remove(img)
            img.save(path)
            await ctx.channel.send("Picture set. Is this okay?", file=discord.File(path))
            players[ctx.author.id].image = path

        else:
            await ctx.send("Attachment is not an image.")


def banner_gen(player):
    if player.role == "Crewmate":
        background = Image.open("crewmate.png")
        if player.image:
            foreground = Image.open(player.image)
            foreground = foreground.resize((750, foreground.height * 750 // foreground.width))
            location = (background.width // 2 - foreground.width // 2, 950 - foreground.height // 2)
            background.paste(foreground, location, foreground)
        background.save(f"banner/{player.member.name}.png")


@bot.command()
async def start(ctx):
    global game_started
    # Check if game has already started
    if game_started:
        await ctx.send("Game has already started.")
        return

    # Check if there are enough players
    if len(players) < 1:
        await ctx.send("Not enough players to start game.")
        return

    # Assign roles
    num_impostors = 1
    if len(players) >= 7:
        num_impostors = 2

    all_players = list(players.values())
    random.shuffle(all_players)

    for i in range(num_impostors):
        await all_players[i].set_role("Impostor")

    for i in range(num_impostors, len(all_players)):
        await all_players[i].set_role("Crewmate")

    await assign_tasks()

    # Send banner to players

    game_started = True
    await ctx.send("Game has started!")


@bot.command()
async def reset(ctx):
    global game_started
    # Check if the user who sent the command is the moderator
    moderator_role = discord.utils.get(ctx.guild.roles, name="Moderator")
    if moderator_role not in ctx.author.roles:
        await ctx.send("Only the game moderator can reset the game.")
        return

    # Delete all player channels
    for player in players.values():
        await player.channel.delete()
        await player.member.remove_roles(discord.utils.get(ctx.guild.roles, name="Player"))

    # Clear the player list
    players.clear()

    game_started = False
    await ctx.send("The game has been reset.")


if __name__ == '__main__':
    bot.run(token)

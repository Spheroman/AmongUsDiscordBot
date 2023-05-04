import random
from dotenv import load_dotenv
import discord
from discord.ext import commands
import os
import json
from rembg.bg import remove
from PIL import Image
import webserver
import multiprocessing
import time

load_dotenv()
token = os.getenv('TOKEN')
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())
server = webserver

players = {}
crewmates = []
impostors = []
game_started = False
last_meeting = 0
sabotage = None
meetings = 2
votes = {}
num_impostors = 1
rand_ids = {}
announcements = discord.utils.get(bot.get_all_channels(), name="announcements")

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
        self.visual = task_dict["visual"]

    def __str__(self):
        return f"{self.name} in {self.location}"


taskjson = json.load(open("tasks.json"))
tasks = []
commontasks = []
for task in taskjson:
    if task["type"] != "common":
        tasks.append(Task(task))
    else:
        commontasks.append(Task(task))
commontasks = random.choices(commontasks, k=2)


class Player:
    def __init__(self, member: discord.Member, channel):
        self.member = member
        self.role = None
        self.alive = True
        self.tasks = []
        self.channel = channel
        self.embed = Embed("Welcome to the game!", "Please wait for people to join.", discord.Color.red())
        self.embedmsg = None
        self.image = f"players/{member.display_name}.png"
        self.meetings = meetings
        self.secret = None

    def __str__(self):
        return self.member.display_name

    async def create_channel(self):
        overwrites = {
            self.member.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            discord.utils.get(self.member.guild.roles, name="Moderator"): discord.PermissionOverwrite(
                read_messages=True),
            self.member.guild.me: discord.PermissionOverwrite(read_messages=True),
            self.member: discord.PermissionOverwrite(read_messages=True)
        }
        category = discord.utils.get(self.member.guild.categories, name="Game Channels")
        channel_name = f"{self.member.display_name.lower()}-private"
        self.channel = await self.member.guild.create_text_channel(channel_name, overwrites=overwrites,
                                                                   category=category)

    def add_task(self, task):
        self.tasks.append(task)

    async def set_role(self, role):
        if role == "Impostor":
            self.embed = Embed("You are an Impostor!",
                               "Your job is to kill all the Crewmates before they complete all of their tasks.",
                               discord.Color.red())
            self.embed.add_field("Kill", "To kill a Crewmate, use the command `!kill <players>`", inline=True)
            self.embed.add_field("Sabotage", "To sabotage, use the command `!sabotage`", inline=True)
            self.embed.set_footer("This message will update throughout the game.")
            self.embedmsg = await self.channel.send(embed=self.embed)
            await self.channel.send(f"Your secret id is {self.secret}. Use this to login to the webpage.")
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
        self.banner = banner_gen(self)
        self.secret = player.secret

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
        self.banner = banner_gen(self)
        self.secret = player.secret

    async def update_embed(self):
        taskstrings = []
        for task in self.tasks:
            taskstrings.append(str(task))
        self.embed.set_tasks("Tasks", "\n".join(taskstrings))
        await self.embedmsg.edit(embed=self.embed)

    async def finish_task(self, task):
        self.tasks.remove(task)
        await self.channel.send(f"Task {task} completed!")


@bot.event
async def on_ready():
    print("Bot is ready.")
    await bot.change_presence(activity=discord.Game(name="Among Us"))
    categories = list(category for i in bot.guilds for category in i.categories)
    for category in categories:
        if category.name == "Game Channels":
            channels = category.channels
            for channel in channels:
                if channel.name != "game-announcements":
                    await channel.delete()
            if "game-announcements" not in [channel.name for channel in channels]:
                await category.create_text_channel("game-announcements")


@bot.command()
async def join(ctx, msg=""):
    if ctx.author.id in players:
        await ctx.send("You are already in the game.")
        return
    # Create players object and store in dictionary
    player = Player(ctx.author, None)
    await player.create_channel()
    await player.member.add_roles(discord.utils.get(ctx.guild.roles, name="Player"))
    player.embedmsg = await player.channel.send(embed=player.embed)
    players[ctx.author.id] = player

    await ctx.send(f"{ctx.author.mention} has joined the game.")
    await picture(ctx, msg)


@bot.command()
async def meeting(ctx):
    if ctx.author.id not in players:
        await ctx.send("You are not in the game.")
        return
    if ctx.channel.name != players[ctx.author.id].channel.name:
        await ctx.message.delete()
        await players[ctx.author.id].channel.send("You can only call an emergency meeting in your channel.")
        return
    if players[ctx.author.id].meetings == 0:
        await ctx.send("You have no meetings left.")
        return
    await announcements.send(f"{ctx.author.mention} has called an emergency meeting. Please go to the meeting area. {discord.utils.get(ctx.guild.roles, name='Player').mention}")
    players[ctx.author.id].meetings -= 1


@bot.command()
async def vote(ctx, member):
    if ctx.author.id not in players:
        await ctx.send("You are not in the game.")
        return
    if ctx.channel.name != players[ctx.author.id].channel.name:
        await ctx.delete()
        players[ctx.author.id].channel.send("You can only vote in your channel.")
        return
    if member.lower() not in list(i.member.display_name.lower() for i in players.values()):
        await ctx.send("That player is not in the game.")
        return
    member = players[list(i.member.id for i in players.values() if i.member.display_name.lower() == member.lower())[0]].member
    if not players[member.id].alive:
        await ctx.send("That player is dead.")
        return
    votes[ctx.author.id] = member.id
    await ctx.send(f"You have voted for {member.display_name}.")
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
        f"Voting results:\n{'/n'.join([f'{players[key].member.display_name}: {players[value].member.display_name}' for key, value in votes.items()])}")
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
        return f"{players[results[0][0]].member.display_name} was voted out."


async def assign_tasks():
    # Assign tasks to players
    for player in players.values():
        player.tasks = []
        for i in commontasks:
            player.tasks.append(i)
        for i in range(4):
            player.tasks.append(random.choice(list(i for i in list(j for j in tasks if j.task_type == "short" and ((j.visual == "false") or (player.role == "Crewmate"))) if i not in player.tasks)))
        for i in range(2):
            player.tasks.append(random.choice(list(i for i in list(j for j in tasks if j.task_type == "long" and ((j.visual == "false") or (player.role == "Crewmate"))) if i not in player.tasks)))

    for player in players.values():
        random.shuffle(player.tasks)
    # Update embeds
    for player in players.values():
        await player.update_embed()


@bot.command()
async def leave(ctx):
    # Check if players is in game
    if ctx.author.id not in players:
        await ctx.send("You are not in the game.")
        return

    # Remove players from game
    player = players[ctx.author.id]
    await player.channel.delete()
    await player.member.remove_roles(discord.utils.get(ctx.guild.roles, name="Player"))
    del players[ctx.author.id]
    await ctx.send(f"{ctx.author.mention} has left the game.")


@bot.command()
async def picture(ctx, msg=""):
    # Check if players is in game
    if ctx.author.id not in players:
        await ctx.send("You are not in the game.")
        return
    if len(ctx.message.attachments) == 0:
        path = f"players/{ctx.author.display_name}.png"
        await ctx.author.display_avatar.save(path)
        if msg == "":
            img = Image.open(path)
            img = remove(img)
            img.save(path)
        await ctx.channel.send("Picture set. Is this okay?", file=discord.File(path))
        players[ctx.author.id].image = path
    else:
        attachment = ctx.message.attachments[0]
        if attachment.content_type.startswith("image"):
            path = f"players/{ctx.author.display_name}.png"
            await attachment.save(path)
            if msg == "":
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
        background.save(f"banner/{player.member.display_name}.png")
        return f"banner/{player.member.display_name}.png"
    if player.role == "Impostor":
        return f"banner/impostor.png"


def impostor_banner():
    loc = 853
    background = Image.open("impostor.png")
    for player in players.values():
        if player.role == "Impostor":
            if num_impostors == 1:
                if player.image:
                    foreground = Image.open(player.image)
                    if foreground.height > foreground.width:
                        foreground = foreground.resize((foreground.width * 750 // foreground.height, 750))
                    else:
                        foreground = foreground.resize((750, foreground.height * 750 // foreground.width))
                    location = (background.width // 2 - foreground.width // 2, 950 - foreground.height // 2)
                    background.paste(foreground, location, foreground)
            else:
                if player.image:
                    foreground = Image.open(player.image)
                    foreground = foreground.resize((750, foreground.height * 750 // foreground.width))
                    location = (loc - foreground.width // 2, 950 - foreground.height // 2)
                    background.paste(foreground, location, foreground)
                    loc += loc
    background.save(f"banner/impostor.png")


@bot.command()
async def start(ctx):
    global rand_ids
    global num_impostors, announcements
    global game_started
    announcements = discord.utils.get(ctx.guild.channels, name="game-announcements")
    nums = random.sample(range(10000, 99999), len(players.values()))
    for player in players.values():
        player.secret = nums.pop(0)
        rand_ids.update({str(player.secret): player})
    server.update(rand_ids)

    # Check if game has already started
    if game_started:
        await ctx.send("Game has already started.")
        return

    # Check if there are enough players
    if len(players) < 1:
        await ctx.send("Not enough players to start game.")
        return

    # Assign roles
    if len(players) >= 7:
        num_impostors = 2

    all_players = list(players.values())
    random.shuffle(all_players)

    for i in range(num_impostors):
        await all_players[i].set_role("Impostor")

    for i in range(num_impostors, len(all_players)):
        await all_players[i].set_role("Crewmate")

    impostor_banner()
    await assign_tasks()

    # Send banner to players
    game_started = True
    await announcements.send("Game has started! Start doing your tasks!")


@bot.command()
async def reset(ctx):
    global game_started
    # Check if the user who sent the command is the moderator
    moderator_role = discord.utils.get(ctx.guild.roles, name="Moderator")
    if moderator_role not in ctx.author.roles:
        await ctx.send("Only the game moderator can reset the game.")
        return

    # Delete all players channels
    for player in players.values():
        await player.channel.delete()
        await player.member.remove_roles(discord.utils.get(ctx.guild.roles, name="Player"))

    # Clear the players list
    players.clear()

    game_started = False
    await ctx.send("The game has been reset.")


async def test():
    await announcements[0].send("test")


def init(token):
    print("Starting bot...")
    bot.run(token)


if __name__ == '__main__':
    cord = multiprocessing.Process(target=init, args=(token,))
    cord.start()
    server.app.run(debug=False)

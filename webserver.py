from flask import Flask, request, session
from bot import bot, test
import asyncio

app = Flask(__name__)
app.secret_key = 'fortnite'

ids = {}

@app.route('/set_id', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        session['code'] = request.form['code']
        return get_name()
    return '''
        <form method="post">
            <label for="name">Paste your code here:</label>
            <input type="text" name="code" id="code" />
            <input type="submit" value="Submit" />
        </form>
    '''


@app.route('/get_name')
def get_name():
    name = session.get('code')
    asyncio.run(test())
    if name:
        return 'Name is: {}'.format(ids[str(name)].display_name)
    else:
        return 'Name not set'


def update(ctx):
    global ids
    ids = ctx
    print(ids)


if __name__ == '__main__':
    app.run(debug=True)
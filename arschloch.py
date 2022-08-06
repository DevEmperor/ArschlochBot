"""
ArschlochBot for the popular card game "Arschloch"
Copyright: Jannis Zahn, 2022
https://github.com/DevEmperor
"""


import discord
from discord.utils import get
from discord.ext import tasks
import asyncio
import random


MSG_ID_QUEUE = 1001058092324237335  # id of the queue-message to edit later
deck = ["7", "8", "9", "10", "J", "Q", "K", "A"]
total_deck = deck * 4
roles = ["K", "VK", "VA", "A"]
players = {}  # dict that stores all player information
afk = False


class Game:  # class that stores all game information
    state = "Queue"
    counter, current, passes, finished, next = 0, 0, 0, 0, 0
    queue = []
    stack = "1-"
    afk, k_traded, vk_traded = False, False, False


bot = discord.Client()
game = Game()


def get_symbols(cards):  # returns a string with all discord icons of the cards separated by spaces
    symbols = {
        "7": ":seven:",
        "8": ":eight:",
        "9": ":nine:",
        "10": ":keycap_ten:",
        "J": ":regional_indicator_j:",
        "Q": ":regional_indicator_q:",
        "K": ":regional_indicator_k:",
        "A": ":regional_indicator_a:",
        "-": ":blue_square:",
        "done": ":white_check_mark:"
    }
    return " ".join(symbols[c] for c in cards)


def get_order():
    order = [o + " (" + players[o]["role"] + ")" for o in list(players.keys())]
    order[game.current] = "**" + order[game.current] + "**"
    return "*Order:* " + " | ".join(f"~~{order[i]}~~" if list(players.values())[i]["deck"][0] == "done" else order[i] for i in range(4))


def next_player():
    game.current = (game.current + 1) % 4
    while list(players.values())[game.current]["deck"][0] == "done":
        game.current = (game.current + 1) % 4


async def reset_game(client):
    game_channel = get(client.get_all_channels(), name="game")
    game.counter, game.current, game.passes, game.finished, game.next = 0, 0, 0, 0, 0
    game.queue = []
    game.stack = "1-"
    game.afk, game.k_traded, game.vk_traded = False, False, False
    global players

    await game_channel.set_permissions(game_channel.guild.default_role, send_messages=True)  # #game-channel can be opened again
    for i, player in enumerate(players.values()):  # remove the private roles from all players
        p_discord = player["discord"]
        await p_discord.remove_roles(get(p_discord.guild.roles, name=f"player_0{i + 1}"))
        await get(p_discord.guild.channels, name=f"player_0{i + 1}").purge()

    players = {}
    game.state = "Queue"
    await print_queue(game_channel)


async def print_queue(channel):  # resend the queue
    msg = await channel.fetch_message(MSG_ID_QUEUE)
    s = "\n".join(f"{i+1}. {q.name}" for i, q in enumerate(game.queue))
    await msg.edit(content=f"**{game.state}: **\n" + (s if s != "" else "empty"))


async def resend_game_state(info):  # update all game messages for all players
    for player in players.values():
        await player["msg_round"].edit(content=f"*Round:* {game.counter + 1}")
        await player["msg_order"].edit(content=get_order())
        await player["msg_deck"].edit(content=get_symbols(player["deck"]))
        await player["msg_stack"].edit(content=get_symbols([game.stack[1:]] * int(game.stack[0])))
        await player["msg_info"].edit(content=info)


@tasks.loop(minutes=15)
async def garbage_collector():  # reset the game if no action was performed during the last 30 minutes
    if len(game.queue) == 0: return

    if game.afk:  # check if nobody did something during the past minutes
        warning = ":exclamation: There was no action for more than 15 minutes. The game will reset in 1 minute if no action is being performed ... :exclamation:"
        if game.state == "Queue":  # send the warning to the channel where users might be active
            await get(bot.get_all_channels(), name="game").send(warning, delete_after=60.0)
        elif game.state in ["Running", "Next", "Trading"]:
            for i in range(4):
                await get(bot.get_all_channels(), name=f"player_0{i + 1}").send(warning, delete_after=60.0)

        await asyncio.sleep(60)  # wait for one minute to give them a chance to act
        if game.afk:  # if still nobody did something, the game resets
            await reset_game(bot)
    game.afk = True


@bot.event
async def on_ready():
    print("Arschloch-Server started successfully. Beep bop.")
    garbage_collector.start()


@bot.event
async def on_message(message):  # MESSAGE_LISTENER
    if message.author == bot.user:
        return

    if message.channel.name == "game":  # everything that happens in the waiting room
        await message.delete()

        if message.content.lower() == ".join" and len(game.queue) < 4 and message.author not in game.queue:
            game.afk = False
            game.queue.append(message.author)
            await print_queue(message.channel)

        elif message.content.lower() == ".quit":
            game.afk = False
            if message.author in game.queue:
                game.queue.remove(message.author)
                await print_queue(message.channel)

        if len(game.queue) == 4 and game.state == "Queue":  # if 4 players were found, the game starts
            game.state = "Running"
            await message.channel.set_permissions(message.guild.default_role, send_messages=False)  # #game-channel has to be closed
            await print_queue(message.channel)
            await message.channel.send("I will now prepare the game; please wait a moment ...", delete_after=10.0)

            random.shuffle(total_deck)
            while total_deck[0] != "7": random.shuffle(total_deck)  # shuffles the deck until the first player gets a 7

            for i, q in enumerate(game.queue):  # fills the players-dict with their info and deck
                players[q.name] = {"discord": q, "deck": sorted(total_deck[i::4], key=lambda x: deck.index(x)), "role": "-"}

            for i, (name, player) in enumerate(players.items()):
                p_discord = player["discord"]
                channel = get(p_discord.guild.text_channels, name=f"player_0{i+1}")

                # give the players their roles and send them to their private channels
                await p_discord.add_roles(get(p_discord.guild.roles, name=f"player_0{i+1}"))

                # all initial game-messages are sent; they will be saved for further editing
                await channel.send("__**Welcome back to the game**__\n\n")

                players[name]["msg_round"] = await channel.send(f"*Round:* 1")
                players[name]["msg_order"] = await channel.send(get_order())
                players[name]["msg_stack"] = await channel.send(":blue_square:")
                players[name]["msg_deck"] = await channel.send(get_symbols(players[name]["deck"]))
                players[name]["msg_info"] = await channel.send(f":white_check_mark: Waiting for {list(players.keys())[0]} ...")

            await message.channel.send("The game-channels are now opened. Please join them to get your deck ...", delete_after=10.0)



    elif "player_0" in message.channel.name:  # everything that happens during the game
        content = message.content
        name = message.author.name
        await message.delete()
        if content.lower() == ".quit":  # if anybody wants to quit during the game, it stops for everyone
            await reset_game(bot)
            return

        if game.state == "Running":
            game.afk = False

            if game.current != list(players.keys()).index(name):  # check if the player is allowed to lay a card
                await players[name]["msg_info"].edit(content=":x: It is not your turn!")
                return

            if content[0].lower() == "p":  # check if the player wants to pass
                if game.stack == "1-":
                    await players[name]["msg_info"].edit(content=":x: You MUST play after you made the trick!")
                    return

                next_player()
                game.passes += 1  # if all other players that are still in the game passed in a row, the trick is complete ...
                if game.passes == sum(p["deck"][0] != "done" for p in players.values()) - 1:
                    game.stack = "1-"  # ... so the stack has to be cleared
                    game.passes = 0
                await resend_game_state(f":white_check_mark: Waiting for {list(players.keys())[game.current]} ...")
                return

            if len(content) < 2 or content[0] not in "1234" or content[1:].upper() not in deck:  # check if the syntax is valid
                await players[name]["msg_info"].edit(content=":x: Invalid syntax!")
                return

            amount = int(content[0])
            card = content[1:].upper()
            if players[name]["deck"].count(card) < amount:  # check if player has enough cards
                await players[name]["msg_info"].edit(content=":x: You don't have enough of these cards!")
                return

            # check if the cards fit to the stack
            if game.stack == "1-" or (amount == int(game.stack[0]) and deck.index(card) > deck.index(game.stack[1:])) \
                    or (amount == 4 and (int(game.stack[0]) < 4 or deck.index(card) > deck.index(game.stack[1:]))):  # check for bomb

                game.stack = content.upper()  # add them to the stack
                for _ in range(amount):  # remove played cards from players deck
                    players[name]["deck"].remove(card)
                next_player()
                game.passes = 0

                if len(players[name]["deck"]) == 0:
                    if card == "A" and not any(p["role"] == "A" for p in players.values()):
                        players[name]["role"] = "A"  # if player ends with A, he becomes Arschloch
                    else:
                        players[name]["role"] = roles[game.finished]
                        game.finished += 1
                    players[name]["deck"].append("done")

                if  sum(p["deck"][0] == "done" for p in players.values()) < 3:  # if not 3 players have finished already ...
                    await resend_game_state(f":white_check_mark: Waiting for {list(players.keys())[game.current]} ...")
                    return

                # if three player finished, the game is done; ask for next round
                players[list(players.keys())[game.current]]["role"] = roles[game.finished]  # last player is (Vize-)Arschloch
                players[list(players.keys())[game.current]]["deck"] = ["done"]  # but his deck is also done
                game.state = "Next"
                await resend_game_state(":white_check_mark: Game is finished. Would you like to continue?")
                for player in players.values():
                    await player["msg_info"].add_reaction("✅")
                    await player["msg_info"].add_reaction("❌")

            else:
                await players[name]["msg_info"].edit(content=":x: Those cards are too low or wrong amount!")
                return



        if game.state == "Trading":  # sharing cards after a game is complete and the next one starts
            game.afk = False
            if players[name]["role"] == "K":  # only react if K or VK asks for cards
                if game.k_traded: return  # players must not trade multiple times

                opp = [p["discord"].name for p in players.values() if p["role"] == "A"][0]  # get A from players
                if len(content) < 3 or "&" not in content or any(content.split("&")[i].strip().upper() not in deck for i in [0, 1]):
                    await players[name]["msg_info"].edit(content=":x: Invalid syntax or cards!")
                    return
                wishes = [content.split("&")[i].strip().upper() for i in [0, 1]]

                if len(players[name]["deck"]) == 8:  # K has not received cards yet
                    if any(wishes.count(w) > players[opp]["deck"].count(w) for w in wishes):
                        await players[name]["msg_info"].edit(content=f":x: {opp} doesn't have one or both of these cards!")
                        return

                    for wish in wishes:
                        players[opp]["deck"].remove(wish)  # remove cards from A
                        players[name]["deck"].append(wish)  # add cards to K
                    players[opp]["deck"].sort(key=lambda x: deck.index(x))
                    players[name]["deck"].sort(key=lambda x: deck.index(x))

                    await players[name]["msg_deck"].edit(content=get_symbols(players[name]["deck"]))
                    await players[name]["msg_info"].edit(content=f":white_check_mark: {opp} gave you {get_symbols(wishes)}. "
                                                          f"Which cards do you give {opp} (e.g. \"7 & 8\")?")
                    await players[opp]["msg_deck"].edit(content=get_symbols(players[opp]["deck"]))
                    await players[opp]["msg_info"].edit(content=f":white_check_mark: {name} took {get_symbols(wishes)} from you ... ")

                
                elif len(players[name]["deck"]) == 10:  # K got his cards; K gives bad cards to A
                    if any(wishes.count(w) > players[name]["deck"].count(w) for w in wishes):
                        await players[name]["msg_info"].edit(content=f":x: You don't have one or both of these cards!")
                        return

                    for wish in wishes:
                        players[name]["deck"].remove(wish)  # remove cards from K
                        players[opp]["deck"].append(wish)  # add cards to A

                    await players[name]["msg_deck"].edit(content=get_symbols(players[name]["deck"]))
                    await players[name]["msg_info"].edit(content=f":white_check_mark: You gave {get_symbols(wishes)} to {opp}.")
                    await players[opp]["msg_deck"].edit(content=get_symbols(players[opp]["deck"]))
                    await players[opp]["msg_info"].edit(content=f":white_check_mark: ... and gave you {get_symbols(wishes)}.")
                    game.k_traded = True


            elif players[name]["role"] == "VK":
                if game.vk_traded: return  # players must not trade multiple times

                content = content.strip().upper()
                opp = [p["discord"].name for p in players.values() if p["role"] == "VA"][0]  # get VA from players
                if content not in deck:
                    await players[name]["msg_info"].edit(content=":x: Invalid card!")
                    return

                if len(players[name]["deck"]) == 8:
                    if content not in players[opp]["deck"]:
                        await players[name]["msg_info"].edit(content=f":x: {opp} doesn't have this card!")
                        return

                    players[opp]["deck"].remove(content)  # remove cards from VA
                    players[name]["deck"].append(content)  # add cards to VK
                    players[opp]["deck"].sort(key=lambda x: deck.index(x))
                    players[name]["deck"].sort(key=lambda x: deck.index(x))

                    await players[name]["msg_deck"].edit(content=get_symbols(players[name]["deck"]))
                    await players[name]["msg_info"].edit(content=f":white_check_mark: {opp} gave you {get_symbols([content])}. "
                                                          f"Which cards do you give {opp} (e.g. \"7\")?")
                    await players[opp]["msg_deck"].edit(content=get_symbols(players[opp]["deck"]))
                    await players[opp]["msg_info"].edit(content=f":white_check_mark: {name} took {get_symbols([content])} from you ... ")

                
                elif len(players[name]["deck"]) == 9:  # VK got his card; VK gives bad card to VA
                    if content not in players[name]["deck"]:
                        await players[name]["msg_info"].edit(content=f":x: You don't have this card!")
                        return

                    players[name]["deck"].remove(content)  # remove cards from VK
                    players[opp]["deck"].append(content)  # add cards to VA

                    await players[name]["msg_deck"].edit(content=get_symbols(players[name]["deck"]))
                    await players[name]["msg_info"].edit(content=f":white_check_mark: You gave {get_symbols([content])} to {opp}.")
                    await players[opp]["msg_deck"].edit(content=get_symbols(players[opp]["deck"]))
                    await players[opp]["msg_info"].edit(content=f":white_check_mark: ... and gave you {get_symbols([content])}.")
                    game.vk_traded = True


            if game.vk_traded and game.k_traded:  # if all players traded their cards, the game begins
                game.state = "Running"
                game.k_traded, game.vk_traded = False, False
                for player in players.values():
                    await player["msg_info"].edit(content=f":white_check_mark: Waiting for {list(players.keys())[game.current]} ...")



@bot.event
async def on_reaction_add(reaction, user):  # REACTIONS_LISTENER
    if user == bot.user:
        return

    # if the game has finished, ask if all players want to continue
    if game.state == "Next" and reaction.message.id in [p["msg_info"].id for p in players.values()]:
        game.afk = False
        if str(reaction.emoji) == "✅":
            game.next += 1
            if game.next < 4: return

            # if all players want to continue, the game needs to reset partially
            game.current, game.passes, game.finished, game.next, game.trades = 0, 0, 0, 0, 0
            game.afk, game.k_traded, game.vk_traded = False, False, False
            game.counter += 1
            game.stack = "1-"
            p_roles = {}

            random.shuffle(total_deck)

            for i, (name, player) in enumerate(players.items()):  # give all players a new deck
                players[name]["deck"] = sorted(total_deck[i::4], key=lambda x: deck.index(x))
                await player["msg_info"].clear_reactions()
                p_roles[player["role"]] = name

            game.current = list(players.keys()).index(p_roles["A"])  # A has to start in the next game

            await resend_game_state(f":white_check_mark: Trading begins ...")
            game.state = "Trading"  # trading cards begins

            for player in players.values():  # send instructions for trading
                instructions = {
                    "A": f"Waiting for {p_roles['K']} to ask for cards ...",
                    "VA": f"Waiting for {p_roles['VK']} to ask for a card ...",
                    "VK": f"{p_roles['VA']} has to exchange a card. Which card do you want from {p_roles['VA']} ?",
                    "K": f"{p_roles['A']} has to exchange two cards. Which cards do you want from {p_roles['A']} (e.g. \"A & K\")?"
                }
                await player["msg_info"].edit(content=":white_check_mark: " + instructions[player["role"]])

        if str(reaction.emoji) == "❌":  # if only one player doesn't want to continue, the game stops
            await reset_game(bot)
            return


bot.run("ID")

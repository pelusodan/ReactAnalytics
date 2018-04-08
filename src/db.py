import traceback
import os
import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL')

def remove_message(msg_id):
    query = 'DELETE FROM MESSAGES WHERE MessageID = %s'

# msgs = (msg_id, team_id, user_id, text)
def add_messages(msgs):

    '''
    try:
        c.executemany('INSERT INTO Messages VALUES(%s, %s, %s);', msgs)
    except Exception as e:
        print(e)
        print(traceback.print_exc())
    '''
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    for m in msgs:
        if not msg_exists(m[0]):
            try:
                msg_tuple = (m.msg_id, m.team_id, m.user_id, m.text)
                c.execute('INSERT INTO Messages VALUES (%s, %s, %s, %s);', m)
            except Exception as e:
                print(e)
    conn.commit()
    conn.close()



def add_message(msg, conn=None):

    close = (conn is None)

    if not conn:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()

    try:
        c.execute('INSERT INTO Messages VALUES (%s, %s, %s, %s);', (msg.msg_id, msg.team_id, msg.user_id, msg.text))
    except Exception as e:
        print(e)
        print(traceback.print_exc())
    conn.commit()
    if close:
        conn.close()


# msgs = (msg_id, team_id, user_id, react_name)
def add_reacts(reacts):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')

    for react in reacts:
        _add_react(conn, react.msg_id, react.team_id, react.user_id, react.react_name)
    conn.commit()
    conn.close()


def _add_react(conn, msg_id, team_id, user_id, react_name):
    c = conn.cursor()
    print('add react')
    print(msg_id + ", " + user_id + ", " + react_name)
    try:
        if _exists_in_message_reacts(conn, msg_id, react_name):
            print('msg exists in MessageReacts')

            query = ('''UPDATE MessageReacts
                    SET Count = Count + 1
                    WHERE MessageReacts.MessageID = %s
                    AND MessageReacts.ReactName = %s''')
            c.execute(query, (msg_id, react_name))
        else:
            c.execute('INSERT INTO MessageReacts VALUES(%s, %s, 1);',(msg_id, react_name))


        if _exists_in_user_reacts(conn, user_id, react_name):
            print('msg exists in UserReacts')
            c.execute('''UPDATE UserReacts
                    SET Count = Count + 1
                    WHERE UserReacts.UserID = %s
                    AND UserReacts.TeamID = %s
                    AND UserReacts.ReactName = %s''',
                      (user_id, team_id, react_name))
        else:
            c.execute('INSERT INTO UserReacts VALUES(%s, %s, %s, 1);',(user_id, team_id, react_name))
    except Exception as e:
        print(e)
        print(traceback.print_exc())

def remove_react(react):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()

    try:
        c.execute('''UPDATE MessageReacts
                SET Count = Count - 1
                WHERE MessageReacts.MessageID = %s
                AND MessageReacts.ReactName = %s''', (react.msg_id, react.react_name))
    except Exception as e:
        print(e)
        print(traceback.print_exc())

    try:
        c.execute('''
              UPDATE UserReacts
              SET Count = Count - 1
              WHERE UserReacts.UserID = %s AND UserReacts.ReactName = %s''', (react.user_id, react.react_name))
    except Exception as e:
        print(e)
        print(traceback.print_exc())

    conn.commit()
    conn.close()


def _exists_in_message_reacts(conn, msg_id, react_name):
    c = conn.cursor()
    c.execute("SELECT * FROM MessageReacts WHERE MessageReacts.MessageID = %s AND MessageReacts.ReactName = %s",
                       (msg_id, react_name))
    result = c.fetchone()
    if not result:
        return False
    return True


def _exists_in_user_reacts(conn, user_id, react_name):
    c = conn.cursor()
    c.execute(
        "SELECT * FROM UserReacts WHERE UserReacts.UserID = %s AND UserReacts.ReactName = %s",
        (user_id, react_name))
    result = c.fetchone()
    if not result:
        return False
    return True

def msg_exists(msg_id, conn = None):
    close = (conn is None)
    if conn is None:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    c.execute('SELECT * FROM Messages WHERE MessageID = %s', (msg_id,))
    row = c.fetchone()
    exists = False
    if row:
        exists = True

    print(exists)
    if close:
        conn.close()

    return exists


def get_reacts_on_user(user_id):
    msgs = get_messages_by_user(user_id)
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    msgs = [(m,) for m in msgs]

    result = c.executemany("SELECT ReactName, sum(MessageReacts.Count) FROM MessageReacts WHERE MessageID = %s GROUP BY ReactName", msgs)
    result = c.fetchall()
    if result is []:
        return {}
    conn.close()
    return {r[0] : r[1] for r in result}

def get_reacts_by_user(user_id):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()

    c.execute(
        "SELECT UserReacts.ReactName, UserReacts.Count FROM UserReacts WHERE UserReacts.UserID = %s",(user_id, ))
    result = c.fetchall()
    if result is []:
        return {}
    reacts = {r[0]: r[1] for r in result}
    conn.close()
    return reacts


def get_reacts_on_message(msg_id):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    c.execute(
        "SELECT ReactName, Count FROM MessageReacts WHERE MessageID = %s",(
            msg_id, ))
    row = c.fetchone()
    reacts = {}
    while row:
        reacts[row[0]] = row[1]
        row = c.fetchone()
    conn.close()
    return reacts

def get_reacts_on_all_messages():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()

    c.execute("SELECT MessageReacts.ReactName, MessageReacts.Count FROM MessageReacts")
    result = c.fetchall()
    if result is None:
        return {}

    reacts = {r[0] : r[1] for r in result}
    conn.close()
    return reacts


def get_messages_by_user(user_id):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()

    c.execute("SELECT MessageID FROM Messages WHERE Messages.UserID = %s", (user_id,))
    result = c.fetchall()
    if result is None:
        return []
    msgs = [row[0] for row in result]
    conn.close()
    return msgs


def get_message_text(team_id, msg_id, conn=None):

    query = "SELECT MessageText FROM Messages WHERE Messages.MessageID = %s"
    text = ''
    if conn is None:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    c.execute(query, (msg_id, ))
    result = c.fetchone()
    if result is None:
        return ''

    text = result[0]
    conn.close()
    return text

def get_all_message_texts():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    c.execute('SELECT MessageText from Messages')
    result = c.fetchall()
    if result is None:
        return []
    texts = [r[0] for r in result]
    conn.close()
    return texts

def get_message_text_from_ids(msg_ids):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    result = {msg_id: get_message_text(conn, msg_id) for msg_id in msg_ids}
    conn.close()
    return result

def get_message_ids():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()

    c.execute("SELECT MessageID FROM Messages")
    row = c.fetchone()
    msg_ids = []
    while row:
        msg_ids.append(row[0])
        row = c.fetchone()
    print(msg_ids)
    conn.close()
    return msg_ids

def get_react_counts():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()

    c.execute('SELECT ReactName, sum(MessageReacts.Count) from MessageReacts GROUP BY ReactName')
    result = c.fetchall()
    print(result)
    if result is None:
        return {}
    reacts = {r[0] : r[1] for r in result}
    conn.close()
    return reacts

def get_react_count(react_name):

    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()
    query = 'SELECT sum(MessageReacts.Count) FROM MessageReacts WHERE ReactName = %s'
    c.execute(query, (react_name, ))
    result = c.fetchall()
    if result is None:
        return []

    conn.close()
    return [r[0] for r in result]

def get_messages_with_react(react_name, text=False):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    c = conn.cursor()

    if text:
        query = '''
                  SELECT MessageText FROM Messages
                  INNER JOIN MessageReacts ON Messages.MessageID=MessageReacts.MessageID
                  WHERE MessageReacts.ReactName = %s AND MessageReacts.Count > 0
                  '''
    else:
        query = "SELECT MessageID FROM MessageReacts WHERE ReactName = %s AND Count > 0"


    c.execute(query, (react_name, ))
    result = c.fetchall()
    print(result)
    if result is None:
        return []
    msgs = [r[0] for r in result]
    conn.close()
    return msgs



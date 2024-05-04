from pypyodbc import connect  # prebuilt package for connecting to SQL database
from riotwatcher import LolWatcher  # prebuilt package for connecting to the API
from datetime import datetime  # prebuilt package for referencing current time and date
from functools import wraps  # prebuilt package for the retry decorator, moving the function to the decorator
from time import sleep  # prebuilt package for stopping the process for a set amount of time


# Dictionary manipulation functions
def without_keys(d, keys):
    # For replicating a dictionary with selected keys removed
    return {k: v for k, v in d.items() if k not in keys}


def with_keys(d, keys):
    # For replicating a dictionary with only the selected keys
    return {k: v for k, v in d.items() if k in keys}


# Retry Decorator, which captures errors and attempts to rerun the function decorated when it fails, lifted from the
# internet, not sure how it works, but it does
def retry(ExceptionToCheck, tries=6, delay=3, backoff=2, logger=None):
    def deco_retry(f):
        @wraps(f)
        def f_retry(*args, **kwargs):
            m_tries, m_delay = tries, delay
            while m_tries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck as e:
                    if m_tries > 5:
                        msg = "%s, Retrying instantly" % (str(e))
                        if logger:
                            logger.warning(msg)
                        else:
                            print(msg)
                        m_tries -= 1
                    else:
                        msg = "%s, Retrying in %d seconds..." % (str(e), m_delay)
                        if logger:
                            logger.warning(msg)
                        else:
                            print(msg)
                        sleep(m_delay)
                        m_tries -= 1
                        if m_tries <= 3:
                            m_delay *= backoff  
                        else:
                            m_delay = 300 * backoff * 2 if m_tries == 3 else 4
            return f(*args, **kwargs)
        return f_retry
    return deco_retry


# Base configuration for database connection and storing details around the API and API hits
class Config:
    connection_string = f"""
    DRIVER={'SQL SERVER'};
    SERVER=BEST-DESKTOP-EU\RIOTGAMES;
    DATABASE=League_of_Legends_V2;
    Trust_Connection=yes;
    """
    connection = connect(connection_string)
    cursor = connection.cursor()

    cursor.execute("SELECT TOP(1) api FROM [api].[ApiKey]")
    api = cursor.fetchall()
    api = api[0][0]
    api_hits = {
        'EUROPE': 0,
        'AMERICAS': 0,
        'ASIA': 0,
        'SEA': 0,
        'EUROPE_Time': datetime.now(),
        'AMERICAS_Time': datetime.now(),
        'ASIA_Time': datetime.now(),
        'SEA_Time': datetime.now()
    }


# Installs a new API key, which is updated every 24 hours
def new_api(newApi):
    query = f"UPDATE [api].[ApiKey] SET api = '{newApi}'"
    Config.cursor.execute(query)
    Config.connection.commit()
    Config.api = newApi
    print('New API Installed - '+Config.api)
    sleep(5)


# allows me to call a tables dimensions from SQL and save it as a dictionary for updating
def table_data(table_name, database=''):
    table_name = table_name.replace('[dbo].[', '')
    table_name = table_name.replace('[ref].[', '')
    table_name = table_name.replace(']', '')
    query = f"SELECT ORDINAL_POSITION, COLUMN_NAME FROM {database}INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = N'{table_name}'"
    Config.cursor.execute(query)
    sql_table = Config.cursor.fetchall()
    sql_table = dict((y, x) for x, y in sql_table)
    for x in sql_table:
        sql_table[x] = None
    return sql_table


# takes in a RegionID and returns AltRegionID, which is the server that region is based on
def region_lookup(Region):
    query = f"SELECT [altRegionId] FROM [ref].[Lu_Regions] WHERE regionId = '{Region}'"
    Config.cursor.execute(query)
    region_list = Config.cursor.fetchall()
    region_id = region_list[0][0]
    return region_id


# required before each API hit to update Config with how many times the API has been hit and how fast
# API only allows 100 hits every 120 seconds per server
def api_count(Region=None):
    AltRegionId = 'EUROPE' if not Region else region_lookup(Region)
    Config.api_hits.update({AltRegionId: Config.api_hits[AltRegionId]+1})
    count = Config.api_hits[AltRegionId]
    if count % 99 == 0:
        seconds = abs(datetime.now() - Config.api_hits[AltRegionId+'_Time']).seconds
        if 120 - seconds > 0:
            sleep(120 - seconds)
        Config.api_hits.update({AltRegionId+'_Time': datetime.now()})


# data_dragon is the collection of lookups provided for multiple ids
# checks if the version saved is the most recent, if it is, does nothing, if not, updates the version
@retry(Exception, tries=6, delay=30)
def data_dragon():
    live_version = LolWatcher(Config.api).data_dragon.versions_all()[0]
    query = "SELECT TOP(1) version FROM [ref].[Lu_Data_Dragon_Version]"
    Config.cursor.execute(query)
    saved_version = Config.cursor.fetchall()[0][0]
    if live_version == saved_version:
        print('Data Dragon already up to date')
    else:
        query = f"UPDATE [ref].[Lu_Data_Dragon_Version] SET version = '{live_version}'"
        Config.cursor.execute(query)
        Config.connection.commit()
        query = "TRUNCATE TABLE [ref].[Lu_Summoner_Spells] TRUNCATE TABLE [ref].[Lu_Items] " \
                "TRUNCATE TABLE [ref].[Lu_Champions] TRUNCATE TABLE [ref].[Lu_Runes] "
        Config.cursor.execute(query)
        Config.connection.commit()
        api_count()
        runes = LolWatcher(Config.api).data_dragon.runes_reforged(live_version)
        sql_table = table_data('[ref].[Lu_Runes]')
        column_number = len(sql_table)
        query = f"INSERT INTO [ref].[Lu_Runes] VALUES ({(column_number - 1) * '?,'} ?)"
        for x in range(0, len(runes)):
            for y in range(0, len(runes[x]['slots'])):
                for z in range(0, len(runes[x]['slots'][y]['runes'])):
                    sql_table.update(with_keys(runes[x]['slots'][y]['runes'][z], ['id', 'key', 'name']))
                    Config.cursor.execute(query, list(sql_table.values()))
                    Config.connection.commit()
        # Adding in rune shards
        query = 'EXEC [ref].[uspPopulate_Lu_Runes_Shards]'
        Config.cursor.execute(query)
        Config.connection.commit()

        api_count()
        champions = LolWatcher(Config.api).data_dragon.champions(live_version)
        sql_table = table_data('[ref].[Lu_Champions]')
        column_number = len(sql_table)
        query = "INSERT INTO [ref].[Lu_Champions] VALUES (" + (column_number - 1) * "?," + "?)"
        for x in range(0, len(champions['data'])):
            champion = list(champions['data'].keys())[x]
            sql_table.update(with_keys(champions['data'][champion], ['id', 'key', 'name']))
            Config.cursor.execute(query, list(sql_table.values()))
            Config.connection.commit()

        api_count()
        items = LolWatcher(Config.api).data_dragon.items(live_version)
        sql_table = table_data('[ref].[Lu_Items]')
        column_number = len(sql_table)
        query = "INSERT INTO [ref].[Lu_Items] VALUES (" + (column_number - 1) * "?," + "?)"
        for x in range(0, len(items['data'])):
            item = list(items['data'].keys())[x]
            sql_table = {x: 'NULL' for x in sql_table}
            sql_table.update({'name': items['data'][item]['name'],
                              'id': item})
            sql_table.update(items['data'][item]['stats'])
            Config.cursor.execute(query, list(sql_table.values()))
            Config.connection.commit()

        api_count()
        summoner_spells = LolWatcher(Config.api).data_dragon.summoner_spells(live_version)
        sql_table = table_data('[ref].[Lu_Summoner_Spells]')
        column_number = len(sql_table)
        query = "INSERT INTO [ref].[Lu_Summoner_Spells] VALUES (" + (column_number - 1) * "?," + "?)"
        for x in range(0, len(summoner_spells['data'])):
            spell = list(summoner_spells['data'].keys())[x]
            sql_table.update(with_keys(summoner_spells['data'][spell], ['id', 'key', 'name']))
            Config.cursor.execute(query, list(sql_table.values()))
            Config.connection.commit()

        print('Data Dragon Updated')


# searches the leaderboards for players who are ranked Masters and above and collects them in [dbo].[Summoner_Rank]
# takes in AltRegionID as an arg, so that only players on that server are collected
# hits the API 3 times per Region, of which there are currently 16 for a total of 48 API hits
# 12 AMERICAS, 6 ASIA, 12 EUROPE and 18 SEA
# first of the 4 major functions called by import_data()
# loop logic = for each region, check challenger, and for each entry in challenger add a row into [dbo].[Summoner_Rank]
#                               check grandmaster, and for each grandmaster add a row into [dbo].[Summoner_Rank]
#                               check master, and for each master add a row into [dbo].[Summoner_Rank]
@retry(Exception, tries=6, delay=30)
def add_high_rank_players(AltRegionID):
    sql_table = table_data('[dbo].[Summoner_Rank]')

    query = f"DELETE FROM [dbo].[Summoner_Rank] WHERE Region IN (SELECT RegionID FROM [ref].[Lu_Regions] WHERE" \
            f" [AltRegionID] = '{AltRegionID}') "
    Config.cursor.execute(query)
    Config.connection.commit()
    query = f"DELETE FROM [dbo].[Summoner_Rank] WHERE Region IN (SELECT RegionID FROM [ref].[Lu_Regions] WHERE" \
            f" [AltRegionID] = '{AltRegionID}') "
    Config.cursor.execute(query)
    Config.connection.commit()
    column_number = len(sql_table)
    query = F"SELECT [regionId] FROM [ref].[Lu_Regions] where AltRegionID = '{AltRegionID}'"
    Config.cursor.execute(query)
    region_list = Config.cursor.fetchall()
    for x in range(0, len(region_list)):
        api_count(region_list[x][0])
        challenger_players = LolWatcher(Config.api).league.challenger_by_queue(region_list[x][0], 'RANKED_SOLO_5x5')
        for y in range(0, len(challenger_players['entries'])):
            sql_table.update(challenger_players['entries'][y])
            challenger_players['queueType'] = challenger_players['queue']
            sql_table.update(with_keys(challenger_players, ['tier', 'leagueId', 'queueType']))
            sql_table.update({'Region': region_list[x][0],
                              'RowUpdateDateTime': datetime.now()})
            query = "INSERT INTO [dbo].[Summoner_Rank] VALUES (" + (column_number - 1) * "?," + "?)"
            Config.cursor.execute(query, list(sql_table.values()))
            Config.connection.commit()
        api_count(region_list[x][0])
        grandmaster_players = LolWatcher(Config.api).league.grandmaster_by_queue(region_list[x][0], 'RANKED_SOLO_5x5')
        for y in range(0, len(grandmaster_players['entries'])):
            sql_table.update(grandmaster_players['entries'][y])
            grandmaster_players['queueType'] = grandmaster_players['queue']
            sql_table.update(with_keys(grandmaster_players, ['tier', 'leagueId', 'queueType']))
            sql_table.update({'Region': region_list[x][0],
                              'RowUpdateDateTime': datetime.now()})
            query = "INSERT INTO [dbo].[Summoner_Rank] VALUES (" + (column_number - 1) * "?," + "?)"
            Config.cursor.execute(query, list(sql_table.values()))
            Config.connection.commit()
        api_count(region_list[x][0])
        masters_players = LolWatcher(Config.api).league.masters_by_queue(region_list[x][0], 'RANKED_SOLO_5x5')
        for y in range(0, len(masters_players['entries'])):
            sql_table.update(masters_players['entries'][y])
            masters_players['queueType'] = masters_players['queue']
            sql_table.update(with_keys(masters_players, ['tier', 'leagueId', 'queueType']))
            sql_table.update({'Region': region_list[x][0],
                              'RowUpdateDateTime': datetime.now()})
            query = "INSERT INTO [dbo].[Summoner_Rank] VALUES (" + (column_number - 1) * "?," + "?)"
            Config.cursor.execute(query, list(sql_table.values()))
            Config.connection.commit()
    # print(f'Masters+ Players on {AltRegionID} collected')


# uses a summonerId to pull details of that account, and insert it into [dbo].[Summoner_Accounts]
# 1 API hit per execution, called by add_high_rank_accounts()
def add_user_id(summoner_id, Region):
    sql_table = table_data('[dbo].[Summoner_Accounts]')
    column_number = len(sql_table)
    api_count(Region)
    user_data = LolWatcher(Config.api).summoner.by_id(Region, summoner_id)

    sql_table.update(user_data)
    sql_table.update({'RowUpdateDateTime': datetime.now(),
                      'Region': Region})
    query = f"INSERT INTO [dbo].[Summoner_Accounts] VALUES ({(column_number - 1) * '?,'}?)"
    Config.cursor.execute(query, list(sql_table.values()))
    Config.connection.commit()


# creates a list of summonerIds to pull from [vw].[vw_Missing_Summoner_Details]
# [vw].[vw_Missing_Summoner_Details] output creates a list of summoners pulled by add_high_rank_players()
# and summoners are filtered out if their data is already collected
# takes in AltRegionID as an arg, so that only players on that server are collected
# Second of the major functions called by import_data()
# hits the API one time per account
# loop logic = for each missing user, insert missing user details into [dbo].[Summoner_Accounts]
@retry(Exception, tries=6, delay=30)
def add_high_rank_accounts(AltRegionID):
    query = f"SELECT [summonerId], [region], AltRegionID FROM [vw].[vw_Missing_Summoner_Details] WHERE AltRegionID " \
            f"= '{AltRegionID}' "
    Config.cursor.execute(query)
    summoner_list = Config.cursor.fetchall()
    print(f'{str(len(summoner_list))} New Summoners to collect for {AltRegionID}')
    for x in range(0, len(summoner_list)):
        summoner_id = summoner_list[x][0]
        region = summoner_list[x][1]
        add_user_id(summoner_id, region)


# Updates the table [vw].[vw_Match_History_Check], which checks if that player has had their match history pulled in the
# last two days. The maximum number of games that can be collected is the last 100 games per account. Based on the
# likelihood that no one will play over 100 games in 2 days. That table is then used as a basis on which summoners data
# is needed to be pulled for. Only games in the last 3 patches are collected using the timestamps and a patch lookup
# takes in AltRegionID as an arg, so that only games on that server are collected
# Third of the major functions called by import_data()
# hits the API one time per account
# loop logic = for each summoner, pull their last 100 games, and for each game, insert a row into [dbo].[Match_List]
@retry(Exception, tries=6, delay=30)
def add_matches(AltRegionID):
    sql_table = table_data('[dbo].[Match_List]')
    column_number = len(sql_table)
    query = f"SELECT [puuid], [Region], [AltRegionID] FROM [vw].[vw_Match_History_Check]" \
            f"WHERE [IncludeFlag] IS NOT NULL AND AltRegionID = '{AltRegionID}' ORDER BY leaguePoints DESC"
    Config.cursor.execute(query)
    summoner_list = Config.cursor.fetchall()
    query = "SELECT [EpochTimeStamp] FROM [vw].[vw_EpochTimeStamp]"
    Config.cursor.execute(query)
    EpochTimeStamp = Config.cursor.fetchall()
    print(f'{len(summoner_list)} Match Histories to collect for {AltRegionID}')
    query = f"INSERT INTO [dbo].[Match_List] VALUES ({(column_number - 1) * '?,'}?)"
    for x in range(0, len(summoner_list)):
        puuid = summoner_list[x][0]
        region_id = summoner_list[x][1]
        alt_region_id = summoner_list[x][2]
        api_count(region_id)
        match_history = LolWatcher(Config.api).match.matchlist_by_puuid(alt_region_id, puuid,
                                                                        type='ranked',
                                                                        count=100,
                                                                        queue=420,
                                                                        start_time=EpochTimeStamp[0][0])
        for y in range(0, len(match_history)):
            sql_table.update({'matchId': match_history[y],
                              'puuid': puuid,
                              'RowUpdateDateTime': datetime.now()})
            Config.cursor.execute(query, list(sql_table.values()))
            Config.cursor.commit()


# Inserts API call data for the details of a match into [dbo].[Match_Details]
# hits the API once per execution. Data from all players is collected, which should include other high rank players,
# removing the chance of the same match being called twice
# called by add_match_details()
def match_details(match_id, RegionId, alt_region_id):
    sql_table = table_data('[dbo].[Match_Details]')
    sql_dimensions = table_data('[dbo].[Match_Details]')
    column_number = len(sql_table)
    api_count(RegionId)
    match_ds = LolWatcher(Config.api).match.by_id(alt_region_id, match_id)
    for x in range(0, len(match_ds['info']['participants'])):
        dict1 = without_keys(match_ds['info']['participants'][x], ['challenges', 'perks'])
        if 'challenges' in match_ds['info']['participants'][x]:
            dict2 = match_ds['info']['participants'][x]['challenges']
        else:
            dict2 = {}
        if x < 5:
            team = 0
            y = x
        else:
            team = 1
            y = x-5
        dict3 = {'Perk1': match_ds['info']['participants'][x]['perks']['statPerks']['defense'],
                 'Perk2': match_ds['info']['participants'][x]['perks']['statPerks']['flex'],
                 'Perk3': match_ds['info']['participants'][x]['perks']['statPerks']['offense'],
                 'Perk4': match_ds['info']['participants'][x]['perks']['styles'][0]['selections'][0]['perk'],
                 'Perk5': match_ds['info']['participants'][x]['perks']['styles'][0]['selections'][1]['perk'],
                 'Perk6': match_ds['info']['participants'][x]['perks']['styles'][0]['selections'][2]['perk'],
                 'Perk7': match_ds['info']['participants'][x]['perks']['styles'][0]['selections'][3]['perk'],
                 'Perk8': match_ds['info']['participants'][x]['perks']['styles'][1]['selections'][0]['perk'],
                 'Perk9': match_ds['info']['participants'][x]['perks']['styles'][1]['selections'][1]['perk'],
                 'gameCreation': match_ds['info']['gameCreation'],
                 'gameVersion': match_ds['info']['gameVersion'],
                 'Ban': match_ds['info']['teams'][team]['bans'][y]['championId']
                 }
        sql_table.update(dict1)
        sql_table.update(dict2)
        sql_table.update(dict3)
        sql_table.update({'matchId': match_id})
        sql_table = with_keys(sql_table, sql_dimensions.keys())
        query = "INSERT INTO [dbo].[Match_Details] VALUES (" + (column_number - 1) * "?," + "?)"
        Config.cursor.execute(query, list(sql_table.values()))
        Config.connection.commit()


# [vw].[vw_Missing_Match_Details] creates an output that displays all the matches from [dbo].[Match_List] that don't
# have a row in [dbo].[Match_Details]. Matches are also filtered on an average LP minimum defined in the view, currently
# set at 200 LP.
# Last of the major functions called by import_data()
# take in AltRegionID as an arg, to only display matches on a particular server
# hits the API once per game, this is where most of the API calls occur.
# loop logic = for each match, insert the match details into [dbo].[Match_Details]
@retry(Exception, tries=6, delay=30)
def add_match_details(AltRegionID):
    query = f"SELECT DISTINCT [matchId], [regionId], [altRegionId], [MatchAverageLP] " \
            f"FROM [vw].[vw_Missing_Match_Details] WHERE IncludeFlag = 1 AND AltRegionID = '{AltRegionID}'" \
            f"ORDER BY [MatchAverageLP] DESC"
    Config.cursor.execute(query)
    match_list = Config.cursor.fetchall()
    print(f'{str(len(match_list))} Match Details to collect for {AltRegionID}')
    for x in range(0, len(match_list)):
        match_id = match_list[x][0]
        RegionId = match_list[x][1]
        match_details(match_id, RegionId, AltRegionID)


def import_players(AltRegionID):

    # print(f'{str(datetime.now())} - add_high_rank_players({AltRegionID}) begin')
    add_high_rank_players(AltRegionID)

    # print(f'{str(datetime.now())} - add_high_rank_accounts({AltRegionID}) begin')
    add_high_rank_accounts(AltRegionID)


import Riot_API_SQLv2  # Scripts defined in Riot_API_SQLv2
from multiprocessing import Process  # prebuilt package for multiprocessing

# begin multiprocessing
if __name__ == "__main__":
    # Add in the daily API Key
    Riot_API_SQLv2.new_api('RGAPI-dc487ccf-1466-48cb-ba82-fa8e430fe73a')
    # data dragon to check lookups are up-to-date
    Riot_API_SQLv2.data_dragon()

    # initialising for the loop that sets processes ['EUROPE', 'ASIA', 'AMERICAS', 'SEA']
    processes = []
    servers = ['EUROPE', 'ASIA', 'AMERICAS', 'SEA']
    num_processes = len(servers)

    query = "EXEC [dbo].[uspPopulate_Summoner_Rank_Backup]"
    Riot_API_SQLv2.Config.cursor.execute(query)
    Riot_API_SQLv2.Config.connection.commit()

    # create a process list for each server
    for x in range(num_processes):
        process = Process(target=Riot_API_SQLv2.import_players, args=(servers[x],))
        processes.append(process)

    # start each process
    for process in processes:
        process.start()

    # end each process
    for process in processes:
        process.join()

    # initialising for the loop that sets processes
    processes = []
    query = "EXEC [dbo].[uspUpdate_Match_List]"
    Riot_API_SQLv2.Config.cursor.execute(query)
    Riot_API_SQLv2.Config.connection.commit()
    print('EXEC [dbo].[uspUpdate_Match_List] Complete')
    # create a process list for each server
    for x in range(num_processes):
        process = Process(target=Riot_API_SQLv2.add_matches, args=(servers[x],))
        processes.append(process)

    # start each process
    for process in processes:
        process.start()

    # end each process
    for process in processes:
        process.join()

    # initialising for the loop that sets processes
    processes = []
    query = "EXEC [dbo].[uspUpdate_Match_List]"
    Riot_API_SQLv2.Config.cursor.execute(query)
    Riot_API_SQLv2.Config.connection.commit()
    print('EXEC [dbo].[uspUpdate_Match_List] Complete')
    # create a process list for each server
    for x in range(num_processes):
        process = Process(target=Riot_API_SQLv2.add_match_details, args=(servers[x],))
        processes.append(process)

    # start each process
    for process in processes:
        process.start()

    # end each process
    for process in processes:
        process.join()

    #query = "EXEC [dbo].[uspDataBuild] @Build = NULL"
    #Riot_API_SQLv2.Config.cursor.execute(query)
    #print('EXEC [dbo].[uspDataBuild] Complete')
    #Riot_API_SQLv2.Config.connection.commit()

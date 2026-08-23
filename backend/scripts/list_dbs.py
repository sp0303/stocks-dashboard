from pymongo import MongoClient

source_uri = "mongodb+srv://mayalifeos4u_db_user:Sharat123@recruitzaa.c2p3q3c.mongodb.net/?appName=recruitzaa"
client = MongoClient(source_uri)

print("Listing all databases in the source cluster:")
for db_name in client.list_database_names():
    print(f"\nDatabase: {db_name}")
    db = client[db_name]
    try:
        collections = db.list_collection_names()
        print(f"  Collections: {collections}")
    except Exception as e:
        print(f"  Could not list collections: {e}")

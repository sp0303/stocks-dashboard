import sys
import argparse
from pymongo import MongoClient

def migrate_database(source_uri, target_uri):
    print("Connecting to source database...")
    source_client = MongoClient(source_uri)
    
    # Extract DB name from connection URI or default to 'recruitzaa'
    # For atlas, it might be in the URI connection string path or default to the default DB
    source_db_name = source_client.get_database().name
    if source_db_name == "test" or not source_db_name:
        source_db_name = "recruitzaa"
    
    print(f"Source database name resolved as: '{source_db_name}'")
    source_db = source_client[source_db_name]

    print("Connecting to target database...")
    target_client = MongoClient(target_uri)
    target_db_name = target_client.get_database().name
    if target_db_name == "test" or not target_db_name:
        target_db_name = "recruitzaa"
    
    print(f"Target database name resolved as: '{target_db_name}'")
    target_db = target_client[target_db_name]

    # Get all collection names
    collections = source_db.list_collection_names()
    print(f"Found {len(collections)} collections to copy: {collections}")

    for coll_name in collections:
        if coll_name.startswith("system."):
            continue
        
        print(f"Copying collection: {coll_name}...")
        source_coll = source_db[coll_name]
        target_coll = target_db[coll_name]

        # Retrieve documents
        docs = list(source_coll.find({}))
        if not docs:
            print(f"Collection {coll_name} is empty. Skipping.")
            continue
        
        print(f"Found {len(docs)} documents in {coll_name}. Writing to target...")
        # Clear existing target collection first to avoid duplicates or keep clean
        target_coll.delete_many({})
        # Insert
        target_coll.insert_many(docs)
        print(f"Successfully copied {coll_name}.")

    print("Database migration completed successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate MongoDB data from Source to Target.")
    parser.add_argument("--source-pass", required=True, help="Password for the source database")
    parser.add_argument("--source-uri", default="mongodb+srv://mayalifeos4u_db_user:{pass}@recruitzaa.c2p3q3c.mongodb.net/recruitzaa?appName=recruitzaa", help="Source URI template containing {pass}")
    parser.add_argument("--target-uri", default="mongodb://recruitzaa:Recruitzaa123@200.234.41.100:27017/recruitzaa?authSource=admin", help="Target database URI")

    args = parser.parse_args()
    
    resolved_source_uri = args.source_uri.replace("{pass}", args.source_pass)
    migrate_database(resolved_source_uri, args.target_uri)

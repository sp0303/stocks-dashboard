from pymongo import MongoClient

uri = "mongodb://recruitzaa:Recruitzaa123@200.234.41.100:27017/recruitzaa?authSource=admin"
client = MongoClient(uri)
db = client.get_database()

print("Watchlists in target:")
for doc in db.watchlists.find():
    print(doc)

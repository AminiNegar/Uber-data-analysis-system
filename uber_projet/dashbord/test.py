
import chromadb
client = chromadb.PersistentClient(path="./local_vector_db")
collection = client.get_collection(name="uber_cancellation_collection")
print(f"number of records in chroma : {collection.count()}")
print(" 5 sample ides :", collection.peek(5)['ids'])
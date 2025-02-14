import chromadb

# Initialize ChromaDB for storing chat history
chroma_client = chromadb.PersistentClient(path="./chroma_chat_db")

# Create or get a collection for chat messages
chat_collection = chroma_client.get_or_create_collection(name="chat_history")

from config.config import chat_collection
from sentence_transformers import SentenceTransformer
import uuid

model = SentenceTransformer("all-MiniLM-L6-v2")  # Convert chat messages into vector embeddings

def save_chat(user_id, message, role="user"):
    chat_id = str(uuid.uuid4())  # Generate a unique chat ID
    embedding = model.encode(message).tolist()

    # Store chat message in ChromaDB
    chat_collection.add(
        ids=[chat_id], 
        embeddings=[embedding], 
        metadatas=[{"user_id": user_id, "message": message, "role": role}]
    )

def get_chat_history(user_id, limit=5):
    # Query ChromaDB for the last 'limit' messages from the user
    results = chat_collection.query(
        query_embeddings=[[0] * model.get_sentence_embedding_dimension()],  # Dummy query vector
        n_results=limit
    )
    
    # Filter results to return only messages from the specified user
    chat_history = [
        metadata for metadata in results["metadatas"][0]
        if metadata["user_id"] == user_id
    ]

    return chat_history

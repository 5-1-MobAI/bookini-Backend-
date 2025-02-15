import chromadb
from chromadb.config import Settings
from firebase_admin import firestore
import firebase_admin
from firebase_admin import credentials
from datetime import datetime
import os
import time

# Initialize Firebase
cred = credentials.Certificate(os.getenv("FIREBASE_CREDENTIALS_PATH"))
firebase_admin.initialize_app(cred)

# Initialize Firestore client
db = firestore.client()

# Initialize ChromaDB client with settings
client = chromadb.PersistentClient(path="./chroma_db")

def get_user_profile(user_id: str):
    """Fetch user profile from Firestore."""
    user_ref = db.collection("users").document(user_id)
    user_data = user_ref.get().to_dict() or {}

    # Debugging logs
    print(f"Retrieved user data for {user_id}: {user_data}")

    profile = {
        "preferences": user_data.get("preferences", []),
        "wishlist": user_data.get("wishlist", []),
        "owned_books": user_data.get("owned_books", [])
    }

    print(f"Extracted profile: {profile}")
    return profile

def get_book_categories(book_ids, collection_name="books"):
    """Retrieve book categories from Firestore."""
    categories = set()

    for book_id in book_ids:
        book_ref = db.collection(collection_name).document(book_id)
        book_data = book_ref.get().to_dict() or {}

        # Extract categories as an array
        book_categories = book_data.get("Category", [])
        
        if isinstance(book_categories, list):
            categories.update([cat for cat in book_categories if cat and cat != "N/A"])
    
    # Debugging
    print(f"Categories found for books: {categories}")
    
    return list(categories)

def search_books_with_categories(categories: list):
    """Search for books matching given categories in Firestore."""
    if not categories:
        print("WARNING: Empty categories list passed to search_books_with_categories")
        return []

    matching_book_ids = set()

    try:
        books_ref = db.collection("books")
        
        for category in categories:
            query = books_ref.where("Category", "array-contains", category)
            books = query.get()

            for book in books:
                matching_book_ids.add(book.id)

        print(f"Found {len(matching_book_ids)} matching books for categories: {categories}")
        return list(matching_book_ids)

    except Exception as e:
        print(f"ERROR during book search: {e}")
        
        # Fallback: fetch random books if query fails
        try:
            books_ref = db.collection("books").limit(20)
            books = books_ref.get()
            fallback_ids = [book.id for book in books]
            print(f"Using fallback: returned {len(fallback_ids)} random books")
            return fallback_ids
        except:
            return []

def get_book_details(book_ids):
    """Fetch book details from Firestore."""
    books = []

    for book_id in book_ids:
        book_ref = db.collection("books").document(book_id)
        book_data = book_ref.get().to_dict()

        if book_data:
            book_data["id"] = book_id
            books.append(book_data)

    return books

def recommend_books(user_id: str):
    """Generate book recommendations for a user."""
    user_profile = get_user_profile(user_id)

    # Collect categories from multiple sources
    wishlist_categories = get_book_categories(user_profile["wishlist"])
    preferred_categories = user_profile["preferences"]
    owned_book_categories = get_book_categories(user_profile["owned_books"])

    all_categories = set(wishlist_categories + preferred_categories + owned_book_categories)

    print(f"Using categories for recommendation: {all_categories}")

    if not all_categories:
        print("WARNING: No categories found for user. Cannot generate recommendations.")
        return []

    recommended_book_ids = search_books_with_categories(list(all_categories))

    # Exclude books the user already owns or has in their wishlist
    filtered_book_ids = [
        book_id for book_id in recommended_book_ids
        if book_id not in user_profile["owned_books"] and book_id not in user_profile["wishlist"]
    ]

    recommendations = get_book_details(filtered_book_ids)

    print(f"Final recommendations after filtering: {len(recommendations)} books")

    return recommendations[:10]  # Limit to top 10 recommendations

def main_recommender(user_id: str = None):
    """Run book recommendations for a specific user or all users."""
    print("Running book recommendations...")

    if user_id:
        print(f"Processing recommendations for user: {user_id}")
        recommendations = recommend_books(user_id)

        if recommendations:
            db.collection("users").document(user_id).update({"recommendations": recommendations})
            print(f"Updated recommendations for user {user_id}: {len(recommendations)} books")
        else:
            print(f"No recommendations found for user {user_id}")

        return recommendations
    else:
        users = db.collection("users").stream()
        all_recommendations = {}

        for user in users:
            current_user_id = user.id
            print(f"Processing user: {current_user_id}")
            recommendations = recommend_books(current_user_id)

            if recommendations:
                db.collection("users").document(current_user_id).update({"recommendations": recommendations})
                print(f"Updated recommendations for user {current_user_id}: {len(recommendations)} books")
                all_recommendations[current_user_id] = recommendations
            else:
                print(f"No recommendations found for user {current_user_id}")

        print(f"Completed recommendations for {len(all_recommendations)} users")
        return all_recommendations

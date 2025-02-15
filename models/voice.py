import speech_recognition as sr
from gtts import gTTS
import pygame
import tempfile
import os
import queue
import sys
import requests
from typing import Dict, Optional
from models.searching import generate_recommendations

class VoiceQueryHandler:
    def __init__(self, handle_user_request_func):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.handle_user_request = handle_user_request_func
        self.response_queue = queue.Queue()
        pygame.mixer.init()
        
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
    
    def listen_for_query(self):
        try:
            with self.microphone as source:
                print("Listening...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
            
            print("Processing speech...")
            text = self.recognizer.recognize_google(audio)
            print(f"Recognized: {text}")
            return text
            
        except sr.WaitTimeoutError:
            self._speak("I didn't hear anything. Please try again.")
            return None
        except sr.UnknownValueError:
            self._speak("I couldn't understand that. Could you please repeat?")
            return None
        except sr.RequestError as e:
            self._speak("There was an error with the speech recognition service.")
            print(f"Error: {str(e)}")
            return None
    
    def _speak(self, text):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
                temp_filename = fp.name
            
            tts = gTTS(text=text, lang='en')
            tts.save(temp_filename)
            
            pygame.mixer.music.load(temp_filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            
            pygame.mixer.music.unload()
        
        except Exception as e:
            print(f"Error in text-to-speech: {str(e)}")
        finally:
            if os.path.exists(temp_filename):
                os.unlink(temp_filename)
    
    def handle_voice_interaction(self, user_id):
        self._speak("Hello! How can I help you find books today?")
        
        while True:
            query = self.listen_for_query()
            if not query:
                continue
                
            if any(exit_phrase in query.lower() for exit_phrase in ["exit", "quit", "goodbye", "bye"]):
                self._speak("Goodbye! Have a great day!")
                break
            
            try:
                result = self.handle_user_request(user_id, query)
                
                if result.get("found_books"):
                    books = result["found_books"]
                    if books:
                        response = f"I found {len(books)} books. Here are the top matches: "
                        for i, book in enumerate(books[:3], 1):
                            response += f"{i}. {book['title']} by {book['author']}. "
                        
                        if result.get("purchase_details"):
                            response += "Would you like to purchase any of these books?"
                    else:
                        response = "I couldn't find any books matching your request."
                else:
                    response = result.get("message", "I'm sorry, I couldn't process your request.")
                
                self._speak(response)
                
                if result.get("purchase_details"):
                    self._handle_purchase_confirmation(result["purchase_details"])
                    
            except Exception as e:
                print(f"Error processing voice query: {str(e)}")
                self._speak("I'm sorry, there was an error processing your request.")
    
    def _handle_purchase_confirmation(self, purchase_details):
        self._speak("Would you like to proceed with the purchase? Please say yes or no.")
        
        while True:
            response = self.listen_for_query()
            if not response:
                continue
                
            response = response.lower()
            if "yes" in response or "yeah" in response:
                total_price = sum(
                    float(detail["price"].split()[0]) 
                    for detail in purchase_details 
                    if detail["price"] != "N/A"
                )
                
                confirmation = (
                    f"Great! The total for {len(purchase_details)} books will be {total_price:.2f}. "
                    "The purchase will be completed using your default payment method. "
                    "You'll receive an email confirmation shortly."
                )
                self._speak(confirmation)
                break
                
            elif "no" in response or "nope" in response:
                self._speak("No problem! Let me know if you'd like to search for different books.")
                break
            
            else:
                self._speak("I didn't catch that. Please say yes or no.")

def fetch_book_details(title: str) -> Optional[Dict]:
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {'q': title, 'key': os.getenv("GOOGLE_BOOKS_API_KEY", "")}
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        if "items" not in data:
            return None
        
        volume_info = data["items"][0].get("volumeInfo", {})
        sale_info = data["items"][0].get("saleInfo", {})
        
        details = {
            "title": volume_info.get("title", "N/A"),
            "author": ", ".join(volume_info.get("authors", [])) if volume_info.get("authors") else "N/A",
            "publisher": volume_info.get("publisher", "N/A"),
            "published_date": volume_info.get("publishedDate", "N/A"),
            "description": volume_info.get("description", "N/A"),
            "thumbnail": volume_info.get("imageLinks", {}).get("thumbnail", "N/A"),
            "categories": ", ".join(volume_info.get("categories", [])) if volume_info.get("categories") else "N/A",
            "price": sale_info.get("listPrice", {}).get("amount", "N/A")
        }
        return details
        
    except Exception as e:
        print(f"Error fetching book details: {str(e)}")
        return None
    
def main_voice():
    handler = VoiceQueryHandler(lambda user_id, query: {"found_books": generate_recommendations(user_id, query)})
    handler.handle_voice_interaction("test_user")    

if __name__ == "__main__":
    def mock_handle_user_request(user_id, query):
        return {"found_books": [{"title": "Sample Book", "author": "John Doe"}], "purchase_details": None}
    
    voice_assistant = VoiceQueryHandler(mock_handle_user_request)
    voice_assistant.handle_voice_interaction("test_user")

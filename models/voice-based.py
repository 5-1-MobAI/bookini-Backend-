from typing import Optional, Dict, List
import speech_recognition as sr
from gtts import gTTS
import pygame
import tempfile
import os
import json
import time
from threading import Thread
import queue
import sys
import os

class VoiceQueryHandler:
    def __init__(self, handle_user_request_func):
        """
        Initialize the voice query handler.
        
        Args:
            handle_user_request_func: Function that handles user requests (your existing function)
        """
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.handle_user_request = handle_user_request_func
        self.response_queue = queue.Queue()
        
        # Initialize pygame mixer for audio playback
        pygame.mixer.init()
        
        # Calibrate for ambient noise
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
    
    def listen_for_query(self) -> Optional[str]:
        """Listen for voice input and convert to text."""
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
    
    def _speak(self, text: str):
        """Convert text to speech and play it."""
        try:
            # Create temporary file for audio
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
                temp_filename = fp.name
            
            # Generate speech
            tts = gTTS(text=text, lang='en')
            tts.save(temp_filename)
            
            # Play audio
            pygame.mixer.music.load(temp_filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            
            # Clean up
            pygame.mixer.music.unload()
            os.unlink(temp_filename)
            
        except Exception as e:
            print(f"Error in text-to-speech: {str(e)}")
    
    def handle_voice_interaction(self, user_id: str):
        """Main loop for voice interaction."""
        self._speak("Hello! How can I help you find books today?")
        
        while True:
            query = self.listen_for_query()
            if not query:
                continue
                
            # Check for exit command
            if any(exit_phrase in query.lower() 
                  for exit_phrase in ["exit", "quit", "goodbye", "bye"]):
                self._speak("Goodbye! Have a great day!")
                break
            
            # Process the query
            try:
                result = self.handle_user_request(user_id, query)
                
                # Handle different types of responses
                if result.get("found_books"):
                    books = result["found_books"]
                    if books:
                        response = f"I found {len(books)} books. "
                        response += "Here are the top matches: "
                        for i, book in enumerate(books[:3], 1):
                            response += f"{i}. {book['title']} by {book['author']}. "
                        
                        if result.get("purchase_details"):
                            response += "Would you like to purchase any of these books?"
                    else:
                        response = "I couldn't find any books matching your request."
                else:
                    response = result.get("message", "I'm sorry, I couldn't process your request.")
                
                self._speak(response)
                
                # If there are purchase details, handle purchase confirmation
                if result.get("purchase_details"):
                    self._handle_purchase_confirmation(result["purchase_details"])
                    
            except Exception as e:
                print(f"Error processing voice query: {str(e)}")
                self._speak("I'm sorry, there was an error processing your request.")
    
    def _handle_purchase_confirmation(self, purchase_details: List[Dict]):
        """Handle the purchase confirmation flow via voice."""
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
                    f"Great! The total for {len(purchase_details)} books "
                    f"will be {total_price:.2f}. "
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

def test_voice_interaction():
    """Test function for voice interaction."""
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from purchase import handle_user_request
    
    voice_handler = VoiceQueryHandler(handle_user_request)
    test_user_id = "test_user_123"
    
    try:
        voice_handler.handle_voice_interaction(test_user_id)
    except KeyboardInterrupt:
        print("\nVoice interaction terminated by user.")
    except Exception as e:
        print(f"Error in voice interaction: {str(e)}")

if __name__ == "__main__":
    test_voice_interaction()
import speech_recognition as sr
import pyttsx3
import google.generativeai as genai
import pygame
import threading
import queue
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import logging
import os
from datetime import datetime
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SpeechTranslator:
    def __init__(self, api_key):
        """Initialize the Speech Translator with Gemini API"""
        self.api_key = api_key
        self.setup_gemini()
        self.setup_speech_recognition()
        self.setup_tts()
        self.setup_audio()
        
        # Translation queues for both directions
        self.english_to_bengali_queue = queue.Queue()
        self.bengali_to_english_queue = queue.Queue()
        
        # Control flags
        self.is_listening_english = False
        self.is_listening_bengali = False
        self.is_running = True
        
        # Translation history
        self.translation_history = []
        
    def setup_gemini(self):
        """Configure Gemini AI for translation"""
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
            logger.info("Gemini AI configured successfully")
        except Exception as e:
            logger.error(f"Error configuring Gemini AI: {e}")
            raise
    
    def setup_speech_recognition(self):
        """Initialize speech recognition with optimized settings"""
        self.recognizer = sr.Recognizer()
        
        # Optimize recognition settings for better speech end detection
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        
        # Speech end detection settings
        self.recognizer.pause_threshold = 1.0      # Wait 1.0 seconds of silence to end phrase
        self.recognizer.operation_timeout = None
        self.recognizer.phrase_threshold = 0.3     # Min audio length to consider as speech
        self.recognizer.non_speaking_duration = 1.0  # Silence duration to confirm end of speech
        
        # Advanced settings for better detection
        self.min_speech_duration = 0.5  # Minimum speech duration
        self.max_speech_duration = 15.0  # Maximum speech duration before forced stop
        self.silence_threshold = 0.7     # Consecutive silence periods to end
        
        # Get available microphones
        self.microphones = sr.Microphone.list_microphone_names()
        logger.info(f"Available microphones: {self.microphones}")
        
        # Use default microphone
        self.microphone = sr.Microphone()
        
        # Calibrate for ambient noise
        with self.microphone as source:
            logger.info("Calibrating for ambient noise...")
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
        
        logger.info("Speech recognition initialized with enhanced end-of-speech detection")
    
    def setup_tts(self):
        """Initialize Text-to-Speech engines for both languages"""
        # English TTS
        self.tts_english = pyttsx3.init()
        voices_en = self.tts_english.getProperty('voices')
        
        # Set English voice (prefer female voice if available)
        for voice in voices_en:
            if 'english' in voice.name.lower() or 'en' in voice.id.lower():
                self.tts_english.setProperty('voice', voice.id)
                break
        
        self.tts_english.setProperty('rate', 150)  # Slower for clarity
        self.tts_english.setProperty('volume', 0.9)
        
        # Bengali TTS - Use Google TTS as fallback
        self.use_google_tts_for_bengali = True
        try:
            # Try to use system TTS for Bengali
            self.tts_bengali = pyttsx3.init()
            voices_bn = self.tts_bengali.getProperty('voices')
            
            bengali_voice_found = False
            for voice in voices_bn:
                if any(keyword in voice.name.lower() for keyword in ['bengali', 'bn', 'bangla']):
                    self.tts_bengali.setProperty('voice', voice.id)
                    bengali_voice_found = True
                    self.use_google_tts_for_bengali = False
                    break
            
            if not bengali_voice_found:
                logger.warning("No Bengali voice found in system TTS, will use Google TTS")
            else:
                self.tts_bengali.setProperty('rate', 140)
                self.tts_bengali.setProperty('volume', 0.9)
                
        except Exception as e:
            logger.warning(f"Bengali TTS initialization failed: {e}, using Google TTS")
            self.use_google_tts_for_bengali = True
        
        logger.info("TTS engines initialized")
    
    def setup_audio(self):
        """Initialize pygame for audio playback"""
        pygame.mixer.init()
        logger.info("Audio system initialized")
    
    def translate_text(self, text, source_lang, target_lang):
        """Translate text using Gemini AI with enhanced prompting for accuracy"""
        try:
            # Enhanced prompt for better translation accuracy
            if source_lang == "English" and target_lang == "Bengali":
                prompt = f"""You are an expert translator specializing in English to Bengali translation. 
                Translate the following English text to Bengali with high accuracy, maintaining the original meaning, tone, and context.
                Consider cultural nuances and use natural Bengali expressions.
                
                English text: "{text}"
                
                Provide only the Bengali translation without any explanations or additional text."""
                
            else:  # Bengali to English
                prompt = f"""You are an expert translator specializing in Bengali to English translation.
                Translate the following Bengali text to English with high accuracy, maintaining the original meaning, tone, and context.
                Consider cultural nuances and use natural English expressions.
                
                Bengali text: "{text}"
                
                Provide only the English translation without any explanations or additional text."""
            
            response = self.model.generate_content(prompt)
            translated_text = response.text.strip()
            
            logger.info(f"Translated '{text}' -> '{translated_text}'")
            return translated_text
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return f"Translation error: {str(e)}"
    
    def speak_text(self, text, language):
        """Convert text to speech"""
        try:
            if language == "English":
                self.tts_english.say(text)
                self.tts_english.runAndWait()
            else:  # Bengali
                if self.use_google_tts_for_bengali:
                    # Use Google TTS for Bengali
                    self.speak_bengali_with_google_tts(text)
                else:
                    # Use system TTS
                    self.tts_bengali.say(text)
                    self.tts_bengali.runAndWait()
            logger.info(f"Spoke: {text}")
        except Exception as e:
            logger.error(f"TTS error: {e}")
            # Fallback to Google TTS for Bengali
            if language == "Bengali":
                try:
                    self.speak_bengali_with_google_tts(text)
                    logger.info(f"Spoke with Google TTS: {text}")
                except Exception as e2:
                    logger.error(f"Google TTS fallback failed: {e2}")
    
    def speak_bengali_with_google_tts(self, text):
        """Use Google TTS for Bengali speech"""
        try:
            from gtts import gTTS
            import tempfile
            import os
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                temp_filename = tmp_file.name
            
            # Generate speech
            tts = gTTS(text=text, lang='bn', slow=False)
            tts.save(temp_filename)
            
            # Play the audio
            pygame.mixer.music.load(temp_filename)
            pygame.mixer.music.play()
            
            # Wait for playback to complete
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            
            # Clean up
            try:
                os.unlink(temp_filename)
            except:
                pass
                
        except ImportError:
            logger.error("gTTS not installed. Please install with: pip install gtts")
            # Try with system voice as last resort
            try:
                self.tts_bengali.say(text)
                self.tts_bengali.runAndWait()
            except:
                logger.error("All TTS methods failed for Bengali")
        except Exception as e:
            logger.error(f"Google TTS error: {e}")
            # Fallback to system TTS
            try:
                self.tts_bengali.say(text)
                self.tts_bengali.runAndWait()
            except:
                logger.error("System TTS fallback also failed")
    
    def listen_and_recognize(self, language="en-US"):
        """Listen and convert speech to text with enhanced end-of-speech detection"""
        try:
            with self.microphone as source:
                logger.info(f"Listening for {language}...")
                
                # Dynamic noise adjustment
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                
                # Listen with enhanced parameters for better speech end detection
                audio = self.recognizer.listen(
                    source, 
                    timeout=2,  # Wait 2 seconds for speech to start
                    phrase_time_limit=self.max_speech_duration  # Max duration per phrase
                )
            
            # Recognition with multiple attempts for better accuracy
            try:
                if language == "bn-BD":  # Bengali
                    text = self.recognizer.recognize_google(audio, language="bn-BD")
                else:  # English
                    text = self.recognizer.recognize_google(audio, language="en-US")
                
                # Validate speech duration
                if len(text.strip()) < 2:  # Too short, likely noise
                    return None
                
                logger.info(f"Recognized ({language}): {text}")
                return text
                
            except sr.UnknownValueError:
                logger.debug("Could not understand audio - likely end of speech or noise")
                return None
            except sr.RequestError as e:
                logger.error(f"Recognition service error: {e}")
                return None
                
        except sr.WaitTimeoutError:
            # This is normal - means no speech detected
            return None
        except Exception as e:
            logger.error(f"Listen error: {e}")
            return None
    
    def english_to_bengali_worker(self):
        """Worker thread for English to Bengali translation"""
        while self.is_running:
            if self.is_listening_english:
                # Update GUI to show listening state
                if hasattr(self, 'update_status_callback'):
                    self.update_status_callback("🎤 Listening for English...")
                
                text = self.listen_and_recognize("en-US")
                if text and len(text.strip()) > 1:
                    # Update GUI to show processing state
                    if hasattr(self, 'update_status_callback'):
                        self.update_status_callback("🔄 Translating...")
                    
                    # Add to history
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.translation_history.append({
                        'timestamp': timestamp,
                        'original': text,
                        'original_lang': 'English',
                        'translated': '',
                        'target_lang': 'Bengali'
                    })
                    
                    # Translate
                    translated = self.translate_text(text, "English", "Bengali")
                    
                    # Update history
                    self.translation_history[-1]['translated'] = translated
                    
                    # Update GUI to show speaking state
                    if hasattr(self, 'update_status_callback'):
                        self.update_status_callback("🔊 Speaking Bengali...")
                    
                    # Speak in Bengali
                    threading.Thread(target=self.speak_text, args=(translated, "Bengali"), daemon=True).start()
                    
                    # Update GUI
                    self.update_gui_callback(f"[{timestamp}] EN: {text}\n[{timestamp}] BN: {translated}\n\n")
                    
                    # Reset status
                    if hasattr(self, 'update_status_callback'):
                        self.update_status_callback("✅ Ready for English...")
            else:
                if hasattr(self, 'update_status_callback'):
                    self.update_status_callback("⏸️ English listening paused")
            
            time.sleep(0.1)
    
    def bengali_to_english_worker(self):
        """Worker thread for Bengali to English translation"""
        while self.is_running:
            if self.is_listening_bengali:
                # Update GUI to show listening state
                if hasattr(self, 'update_status_callback'):
                    self.update_status_callback("🎤 Listening for Bengali...")
                
                text = self.listen_and_recognize("bn-BD")
                if text and len(text.strip()) > 1:
                    # Update GUI to show processing state
                    if hasattr(self, 'update_status_callback'):
                        self.update_status_callback("🔄 Translating...")
                    
                    # Add to history
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self.translation_history.append({
                        'timestamp': timestamp,
                        'original': text,
                        'original_lang': 'Bengali',
                        'translated': '',
                        'target_lang': 'English'
                    })
                    
                    # Translate
                    translated = self.translate_text(text, "Bengali", "English")
                    
                    # Update history
                    self.translation_history[-1]['translated'] = translated
                    
                    # Update GUI to show speaking state
                    if hasattr(self, 'update_status_callback'):
                        self.update_status_callback("🔊 Speaking English...")
                    
                    # Speak in English
                    threading.Thread(target=self.speak_text, args=(translated, "English"), daemon=True).start()
                    
                    # Update GUI
                    self.update_gui_callback(f"[{timestamp}] BN: {text}\n[{timestamp}] EN: {translated}\n\n")
                    
                    # Reset status
                    if hasattr(self, 'update_status_callback'):
                        self.update_status_callback("✅ Ready for Bengali...")
            else:
                if hasattr(self, 'update_status_callback'):
                    self.update_status_callback("⏸️ Bengali listening paused")
            
            time.sleep(0.1)
    
    def start_english_listening(self):
        """Start listening for English"""
        self.is_listening_english = True
        logger.info("Started English listening")
    
    def stop_english_listening(self):
        """Stop listening for English"""
        self.is_listening_english = False
        logger.info("Stopped English listening")
    
    def start_bengali_listening(self):
        """Start listening for Bengali"""
        self.is_listening_bengali = True
        logger.info("Started Bengali listening")
    
    def stop_bengali_listening(self):
        """Stop listening for Bengali"""
        self.is_listening_bengali = False
        logger.info("Stopped Bengali listening")
    
    def save_history(self, filename="translation_history.json"):
        """Save translation history to file"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.translation_history, f, ensure_ascii=False, indent=2)
            logger.info(f"History saved to {filename}")
        except Exception as e:
            logger.error(f"Error saving history: {e}")
    
    def load_history(self, filename="translation_history.json"):
        """Load translation history from file"""
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    self.translation_history = json.load(f)
                logger.info(f"History loaded from {filename}")
                return True
        except Exception as e:
            logger.error(f"Error loading history: {e}")
        return False
    
    def stop(self):
        """Stop the translator"""
        self.is_running = False
        self.is_listening_english = False
        self.is_listening_bengali = False
        logger.info("Translator stopped")

class TranslatorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Real-time Speech Translator (English ↔ Bengali)")
        self.root.geometry("900x700")
        self.root.configure(bg='#f0f0f0')
        
        self.translator = None
        self.setup_gui()
    
    def setup_gui(self):
        """Setup the GUI interface"""
        # Title
        title_label = tk.Label(self.root, text="🗣️ Real-time Speech Translator", 
                              font=("Arial", 20, "bold"), bg='#f0f0f0', fg='#2c3e50')
        title_label.pack(pady=10)
        
        # API Key Frame
        api_frame = ttk.LabelFrame(self.root, text="Configuration", padding=10)
        api_frame.pack(fill="x", padx=20, pady=5)
        
        tk.Label(api_frame, text="Gemini API Key:").pack(anchor="w")
        self.api_key_entry = tk.Entry(api_frame, width=60, show="*")
        self.api_key_entry.pack(fill="x", pady=(0, 10))
        
        self.initialize_btn = tk.Button(api_frame, text="Initialize Translator", 
                                       command=self.initialize_translator,
                                       bg='#3498db', fg='white', font=("Arial", 10, "bold"))
        self.initialize_btn.pack()
        
        # Control Frame
        control_frame = ttk.LabelFrame(self.root, text="Controls", padding=10)
        control_frame.pack(fill="x", padx=20, pady=5)
        
        # English controls
        english_frame = tk.Frame(control_frame)
        english_frame.pack(fill="x", pady=5)
        
        tk.Label(english_frame, text="🇺🇸 English Speaker:", font=("Arial", 12, "bold")).pack(side="left")
        self.en_listen_btn = tk.Button(english_frame, text="Start Listening", 
                                      command=self.toggle_english_listening,
                                      bg='#27ae60', fg='white', state='disabled')
        self.en_listen_btn.pack(side="right", padx=5)
        
        # Bengali controls
        bengali_frame = tk.Frame(control_frame)
        bengali_frame.pack(fill="x", pady=5)
        
        tk.Label(bengali_frame, text="🇧🇩 Bengali Speaker:", font=("Arial", 12, "bold")).pack(side="left")
        self.bn_listen_btn = tk.Button(bengali_frame, text="Start Listening", 
                                      command=self.toggle_bengali_listening,
                                      bg='#27ae60', fg='white', state='disabled')
        self.bn_listen_btn.pack(side="right", padx=5)
        
        # Status
        self.status_label = tk.Label(control_frame, text="Status: Not initialized", 
                                    font=("Arial", 10), fg='#e74c3c')
        self.status_label.pack(pady=5)
        
        # Translation Display
        display_frame = ttk.LabelFrame(self.root, text="Live Translations", padding=10)
        display_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        self.translation_display = scrolledtext.ScrolledText(display_frame, height=15, 
                                                           font=("Consolas", 10))
        self.translation_display.pack(fill="both", expand=True)
        
        # Bottom Frame
        bottom_frame = tk.Frame(self.root, bg='#f0f0f0')
        bottom_frame.pack(fill="x", padx=20, pady=10)
        
        self.save_btn = tk.Button(bottom_frame, text="Save History", 
                                 command=self.save_history, state='disabled',
                                 bg='#9b59b6', fg='white')
        self.save_btn.pack(side="left", padx=5)
        
        self.clear_btn = tk.Button(bottom_frame, text="Clear Display", 
                                  command=self.clear_display, state='disabled',
                                  bg='#e67e22', fg='white')
        self.clear_btn.pack(side="left", padx=5)
        
        # Instructions
        instructions = """
Instructions:
1. Enter your Gemini API key and click 'Initialize Translator'
2. Click 'Start Listening' for the appropriate language
3. Speak clearly into your microphone
4. The system will translate and speak the translation in real-time
5. Both speakers can talk simultaneously for natural conversation flow
        """
        
        tk.Label(bottom_frame, text=instructions, justify="left", 
                font=("Arial", 9), bg='#f0f0f0', fg='#7f8c8d').pack(side="right")
    
    def initialize_translator(self):
        """Initialize the translator with API key"""
        api_key = self.api_key_entry.get().strip()
        if not api_key:
            messagebox.showerror("Error", "Please enter your Gemini API key")
            return
        
        try:
            self.translator = SpeechTranslator(api_key)
            self.translator.update_gui_callback = self.update_translation_display
            self.translator.update_status_callback = self.update_status
            
            # Start worker threads
            self.en_thread = threading.Thread(target=self.translator.english_to_bengali_worker, daemon=True)
            self.bn_thread = threading.Thread(target=self.translator.bengali_to_english_worker, daemon=True)
            
            self.en_thread.start()
            self.bn_thread.start()
            
            # Enable controls
            self.en_listen_btn.config(state='normal')
            self.bn_listen_btn.config(state='normal')
            self.save_btn.config(state='normal')
            self.clear_btn.config(state='normal')
            self.initialize_btn.config(state='disabled')
            
            self.status_label.config(text="Status: Ready to translate! 🎤", fg='#27ae60')
            
            messagebox.showinfo("Success", "Translator initialized successfully!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to initialize translator: {str(e)}")
    
    def toggle_english_listening(self):
        """Toggle English listening"""
        if not self.translator:
            return
        
        if not self.translator.is_listening_english:
            self.translator.start_english_listening()
            self.en_listen_btn.config(text="Stop Listening", bg='#e74c3c')
        else:
            self.translator.stop_english_listening()
            self.en_listen_btn.config(text="Start Listening", bg='#27ae60')
    
    def toggle_bengali_listening(self):
        """Toggle Bengali listening"""
        if not self.translator:
            return
        
        if not self.translator.is_listening_bengali:
            self.translator.start_bengali_listening()
            self.bn_listen_btn.config(text="Stop Listening", bg='#e74c3c')
        else:
            self.translator.stop_bengali_listening()
            self.bn_listen_btn.config(text="Start Listening", bg='#27ae60')
    
    def update_status(self, status_text):
        """Update the status label"""
        if hasattr(self, 'status_label'):
            self.status_label.config(text=f"Status: {status_text}", fg='#2980b9')
    
    def update_translation_display(self, text):
        """Update the translation display"""
        self.translation_display.insert(tk.END, text)
        self.translation_display.see(tk.END)
    
    def save_history(self):
        """Save translation history"""
        if self.translator:
            self.translator.save_history()
            messagebox.showinfo("Success", "Translation history saved!")
    
    def clear_display(self):
        """Clear the translation display"""
        self.translation_display.delete(1.0, tk.END)
    
    def on_closing(self):
        """Handle window closing"""
        if self.translator:
            self.translator.stop()
        self.root.destroy()
    
    def run(self):
        """Run the GUI application"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

def main():
    """Main function to run the application"""
    try:
        app = TranslatorGUI()
        app.run()
    except Exception as e:
        logger.error(f"Application error: {e}")
        print(f"Error starting application: {e}")

if __name__ == "__main__":
    main()
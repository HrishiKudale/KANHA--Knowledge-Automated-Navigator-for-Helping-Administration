import os
import sqlite3
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import nltk
import spacy
import fitz  # PyMuPDF
import re

nltk.download('punkt')

app = Flask(__name__)
socketio = SocketIO(app)

# Load the spaCy model
nlp = spacy.load('en_core_web_md')

def setup_database():
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS faq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS website_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chatbot_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Add initial data
    cursor.execute('INSERT INTO faq (question, answer) VALUES (?, ?)', ("What services do you offer?", "https://rtsnmmconline.com/pages/home.php"))
    cursor.execute('INSERT INTO faq (question, answer) VALUES (?, ?)', ("I want to register a complaint", "You can report issues through our online portal: https://www.nmmc.gov.in/navimumbai/grievance."))
    cursor.execute('INSERT INTO faq (question, answer) VALUES (?, ?)', ("complaint", "You can report issues through our online portal: https://www.nmmc.gov.in/navimumbai/grievance."))
    cursor.execute('INSERT INTO faq (question, answer) VALUES (?, ?)', ("RTI", "RTI:https://rtionline.maharashtra.gov.in/"))
    cursor.execute('INSERT INTO faq (question, answer) VALUES (?, ?)', ("Office Address", "Ground Floor, Sector-15 A,Palm Beach Junction, CBD Belapur,Navi Mumbai,Maharashtra-400614."))
    cursor.execute('INSERT INTO faq (question, answer) VALUES (?, ?)', ("contact/phone", "02227567071 "))
    conn.commit()
    conn.close()

setup_database()

def log_website_visit():
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO website_visits DEFAULT VALUES')
    conn.commit()
    conn.close()

def log_chatbot_interaction():
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO chatbot_interactions DEFAULT VALUES')
    conn.commit()
    conn.close()

def get_statistics():
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM website_visits')
    website_visits_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM chatbot_interactions')
    chatbot_interactions_count = cursor.fetchone()[0]
    conn.close()
    return website_visits_count, chatbot_interactions_count

# Function to fetch answers from the database
def get_answer_from_database(user_input):
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    cursor.execute("SELECT answer FROM faq WHERE question LIKE ?", ('%' + user_input + '%',))
    answer = cursor.fetchone()
    conn.close()
    return answer[0] if answer else None

def get_hyperlinks_from_pdf(pdf_path):
    links = {}
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            for link in page.get_links():
                uri = link.get('uri')
                if uri:
                    rect = link['from']
                    text = page.get_textbox(rect).get_text().strip()
                    links[text] = uri
    except Exception as e:
        print(f"Error extracting links from PDF: {e}")
    
    return links

def get_answer_from_pdf(user_input):
    pdf_path = 'E:\\NMMC_Chatbot\\Frequently Asked Questions.pdf'  # Replace with your PDF file path
    if not os.path.exists(pdf_path):
        return None
    keyword = user_input.lower()
    doc = fitz.open(pdf_path)
    text = ''
    for page_num in range(len(doc)):
        text += doc[page_num].get_text()
    # Regex pattern to extract Q&A pairs
    qa_pairs = re.findall(r'Q\.\s*(.*?)\s*A\.\s*(.*?)\s*(?=Q\.|$)', text, re.DOTALL)
    # Process user input
    user_input_doc = nlp(user_input)
    best_match = None
    best_similarity = 0.0
    for question, answer in qa_pairs:
        question_doc = nlp(question)
        similarity = user_input_doc.similarity(question_doc)
        if similarity > best_similarity:
            best_similarity = similarity
            best_match = answer.strip()
    # Replace URLs in the answer with clickable links
    hyperlinks = get_hyperlinks_from_pdf(pdf_path)
    if best_match:
        for keyword, url in hyperlinks.items():
            best_match = best_match.replace(url, f'<a href="{url}">{keyword}</a>')
    return best_match

def get_similar_question(user_input):
    # Check if the user input matches any of the options
    answer_from_database = get_answer_from_database(user_input)
    if answer_from_database:
        return answer_from_database
    # Check for specific keywords and provide appropriate response
    if 'feedback' in user_input.lower():
        return "Click on this link to register complaint: <a href='https://www.nmmc.gov.in/navimumbai/feedback'>Feedback</a>."
    elif 'complaint' in user_input.lower():
        return "Click on this link to register complaint: <a href='https://www.nmmc.gov.in/navimumbai/grievance'>Grievance</a>."
    elif 'birth certificate' in user_input.lower():
        return "Click on this link for: <a href='https://www.nmmc.gov.in/navimumbai/assets/251/2020/01/mediafiles/birth.pdf'>Birth Certificate</a>."
    elif 'death certificate' in user_input.lower():
        return "Click on this link for: <a href='https://www.nmmc.gov.in/navimumbai/assets/251/2018/10/mediafiles/death_certificate.pdf'>Death Certificate</a>."
    elif 'property tax' in user_input.lower():
        return "Click on this link to pay: <a href='https://www.nmmc.gov.in/property-tax2'>Property Tax</a>."
    elif 'water bill' in user_input.lower():
        return "Click on this link to pay: <a href='https://www.nmmc.gov.in/water-bill'>Water Bill</a>."
    # Check for simple greetings
    greetings = ["hi", "hey", "hello", "good morning", "good afternoon", "how are you?"]
    if user_input.lower() in greetings:
        return "Hello! How can I help?"
    identity = ["who are you?"]
    if user_input.lower() in identity:
        return "I am your Virtual Assistant, NMMC Chatbot!"
    # If no matching answer is found, try to find in the PDF
    answer_from_pdf = get_answer_from_pdf(user_input)
    if answer_from_pdf:
        return answer_from_pdf
    # If still no matching answer, provide a generic response
    return "I'm not sure I understand. Could you please rephrase?"

# Function to append questions to a text file
def append_unanswered_question(question):
    questions_file = 'questions.txt'
    with open(questions_file, 'a') as f:
        f.write(question + '\n')

@app.route('/')
def home():
    log_website_visit()  # Log the website visit
    return render_template('index.html')

@app.route('/statistics')
def statistics():
    website_visits_count, chatbot_interactions_count = get_statistics()
    return render_template('statistics.html', website_visits=website_visits_count, chatbot_interactions=chatbot_interactions_count)

@socketio.on('message')
def handle_message(msg):
    log_chatbot_interaction()  # Log the chatbot interaction
    response = get_similar_question(msg)
    if response is None or "I'm not sure I understand" in response:
        append_unanswered_question(msg)
    emit('response', response)

if __name__ == '__main__':
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)

# this script is used to perform a google search and extract the relevant information from the search results based on a 
# distillbert question ansering model. 
# (not used in the final version of the project since the model was not able to reply with accurate answes)
import os
import re
import numpy as np
import pandas as pd
import psutil
import requests
import yaml
import spacy
import random
import time
import torch
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sklearn.metrics.pairwise import cosine_similarity
from transformers import pipeline, AutoTokenizer, AutoModel
from urllib.parse import urlparse

#loading the configuration variables from the config.yaml file
def load_config(filename='my_config.yaml'):
    with open(filename, 'r') as f:
        config = yaml.safe_load(f)
    return config

config = load_config("my_config.yaml")
driver_path = config['chromedriver_path']
chromium_path = config['chromium_path']
max_results = config['max_results']
max_sentences = config['max_sentences']
language = config['language']
url_blacklist = config['url_blacklist']
tag_blacklist = config['tag_blacklist']
type_blacklist = config['type_blacklist']
windowed = config['windowed']
window_size = config['window_size']
overlap_rate = config['overlap_rate']

#loading the spacy model based on the language - this is used for sentence tokenization
#if __name__ == "__main__":
if language == "en":
    nlp = spacy.load("en_core_web_sm")
elif language == "it":
    nlp = spacy.load("it_core_news_sm") 
elif language == "es":
    nlp = spacy.load("es_core_news_sm")
else:
    raise Exception("ERROR: LANGUAGE NOT CORRECT - should be set as either 'en', 'it' or 'es'")

# Initialize the QA pipeline
qa_pipeline = pipeline("question-answering", model="distilbert-base-cased-distilled-squad")

# List of common user agents
user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
]

def get_random_user_agent():
    return random.choice(user_agents)

def google_search(query: str, date: str = "") -> str:
    """
    Get the google search results given a query and a date (date is optional)
    
    Args:
        query: the query that will be used to perform the search
        date: optional, results after this date will be excluded
    Returns:
        A sting containing the list of website given by the search results along with a snippet of their content.
    """
    formatted_results = "Google: "+query+" \n "
    if date != "":
        date = pd.to_datetime(date).date()
        query += " before:" + str(date)
        #print("Query with date:", query)

    search_results = get_search_results(query)
    n_good_results = 0
    for result in search_results:
        print("GETTING page:", result)
        if result!="NULL":
            try:
                text = get_all_text(result)
                n_good_results += 1
                formatted_results += str(n_good_results) + ". " + get_domain(result) +": " +web_question_answering(query, text)+" \n"
                #if we have reached the maximum number of results, we stop
                if n_good_results==max_results:
                    break
            except Exception as e:
                print("Failed to fetch page:", result)
                print(e)
                continue
    return formatted_results
        
def kill_process_and_children(pid):
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.NoSuchProcess:
        pass

def get_domain(url: str) -> str:
    """
    Extracts the domain name from a given URL.
    
    Args:
        url (str): The URL from which to extract the domain.
    
    Returns:
        str: The domain name.
    """
    # Parse the URL
    parsed_url = urlparse(url)
    # Extract the netloc (network location part)
    domain = parsed_url.netloc
    # Remove 'www.' if present
    if domain.startswith("www."):
        domain = domain[4:]
    return domain

def filter_urls(urls):
    """
    Filters a list of URLs based on validity and allowed domains.

    Args:
        urls : A list of URLs to be filtered.

    Returns:
        list: A filtered list of URLs that are valid and belong to allowed domains.
    """

    def is_valid_url(url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc]) and not url.endswith(".pdf")
        except ValueError:
            return False
        
    def is_allowed_domain(url):
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        return not any(excluded in domain for excluded in url_blacklist)
    
    def is_allowed_type(url):
        return not any(url.endswith(excluded) for excluded in type_blacklist)
    
    filtered_urls = [
        url for url in urls
        if is_valid_url(url) and is_allowed_domain(url) and is_allowed_type(url)
    ]
    
    # Remove duplicate results from the same domain
    filtered_domains = [get_domain(url) for url in filtered_urls]
    filtered_urls = [
        filtered_urls[i] for i in range(len(filtered_urls))
        if get_domain(filtered_urls[i]) not in filtered_domains[:i]
    ]
    return filtered_urls

def save_soup_to_file(soup, filename):
    """
    Save a BeautifulSoup object to a file.

    Args:
        soup : The BeautifulSoup object to save.
        filename : The name of the file to save the BeautifulSoup object to.
    """
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(str(soup))

def get_all_text(url, max_retries=3, delay=1):
    headers = {
        'User-Agent': get_random_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.google.com/',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    session = requests.Session()
    for attempt in range(max_retries):
        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()  # Raise an exception for bad status codes

            # Check the content type to determine if it's a webpage or a downloadable file
            content_type = response.headers.get('Content-Type')
            if 'text/html' not in content_type:
                raise Exception(f"URL does not point to an HTML page, content type: {content_type}")

            soup = BeautifulSoup(response.text, 'html.parser')
            for element in soup(tag_blacklist):
                element.decompose()
            text = soup.get_text(separator=' ')
            text = text.replace('\xa0', ' ')
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()

            return text
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(delay * (attempt + 1))  # Exponential backoff
            else:
                print("Max retries reached. Could not scrape the website.")
                raise Exception("Failed to fetch page")


def get_search_results(query, keep_browser_open=False):
    """
    Get the search results for a given query. Uses Selenium to scrape the search results from Google.
    
    Args:
        query: The query to search for.
        keep_browser_open: Whether to keep the browser open after scraping the search results.
    
    Returns:
        list: The URLs of the search results.
    """
    chrome_options = Options()
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-search-engine-choice-screen")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--silent")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

    if os.name == 'nt':
        os.environ['WDM_LOG_LEVEL'] = '0'
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    else:
        chrome_options.add_argument("--log-path=/dev/null")

    service = Service(driver_path)
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        driver.get('https://www.google.com')
        
        wait = WebDriverWait(driver, 10)
        try:
            accept_cookies_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[text()="Accetta tutto"]')))
            #accept_cookies_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[text()="Accept all"]')))
            
            accept_cookies_button.click()
        except Exception as e:
            print("Cookie consent dialog not found or already accepted.")
        search_box = wait.until(EC.element_to_be_clickable((By.NAME, 'q')))
        
        search_box.send_keys(query)
        search_box.send_keys(Keys.RETURN)
        
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.yuRUbf')))
        
        results = driver.find_elements(By.CSS_SELECTOR, "div.g div.yuRUbf a")
        #print("Search results found:", len(results))
        search_results = []
        for result in results:
            try:
                search_results.append(result.get_attribute("href"))
            except Exception as e:
                search_results.append("NULL")
        search_results = filter_urls(search_results)
        return search_results

    finally:
        if not keep_browser_open:
            driver.close()
            driver.quit()
            kill_process_and_children(service.process.pid)

def get_embeddings(sentences):
    #return [model(sentence)[0][0] for sentence in sentences]
    inputs = tokenizer(sentences, padding=True, truncation=True, return_tensors="pt", max_length=512)
    with torch.no_grad():
        outputs = similarity_model(**inputs)
    return outputs.last_hidden_state.mean(dim=1)
    

def remove_questions(sentences):
    return [sentence for sentence in sentences if "?" not in sentence]

def calculate_relevance_score(query_embedding, sentence_embedding, query_tokens, sentence_tokens):
    cos_sim = cosine_similarity(query_embedding, sentence_embedding)[0][0]
    
    # Calculate token overlap
    query_set = set(query_tokens)
    sentence_set = set(sentence_tokens)
    overlap = len(query_set.intersection(sentence_set)) / len(query_set)
    
    # Combine cosine similarity and token overlap
    relevance_score = (1-overlap_rate) * cos_sim + overlap_rate * overlap
    return relevance_score

def answer_question(question, context):
    result = qa_pipeline(question=question, context=context)
    return result['answer'], result['score']

def web_question_answering(query, text):
    # Scrape and preprocess the website content
    doc = nlp(text)
    sentences = [sent.text for sent in doc.sents]
    sentences = remove_questions(sentences)
    processed_text = ' '.join([sentence.strip() for sentence in sentences if len(sentence.split()) > 5])

    # Get the answer
    answer, confidence = answer_question(query, processed_text)

    return f"Answer: {answer}\nConfidence: {confidence:.2f}"

# Example usage
print(google_search("is new york city commute time longest in the nation?", date="2024-03-03"))
# -*- coding: utf-8 -*-
"""wikipediaAPI.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1vmtzmks8rqcRsCBdkkSODyt6zsXSmZww
"""

# !pip install transformers
# !pip install wikipedia

import requests
from transformers import pipeline
import wikipedia

# Load the fact-checking pipeline
fact_checking_pipeline = pipeline("zero-shot-classification")

# Define the claim to fact-check
claim = "photosynthesis in plants"

# Define potential labels for fact-checking
candidate_labels = ["True", "Half True", "Half False", "False"]

# Use Wikipedia API to search for the main topic related to the claim
search_results = wikipedia.search(claim)

if search_results:
    # Get the page summary of the first search result
    main_topic = search_results[0]
    page_summary = wikipedia.page(main_topic).content

    # Extract sentences mentioning "climate change" from the page summary
    relevant_sentences = [sentence.strip() for sentence in page_summary.split(".") if "age" in sentence.lower()]

    print(page_summary)

    # write page summary to a file
    with open("../page_summary.txt", "w", encoding="utf-8")  as file:
        file.write(page_summary)

    # Print out the relevant sentences
    print("Sentences mentioning 'climate change' from Wikipedia article:\n")
    for idx, sentence in enumerate(relevant_sentences, 1):
        print(f"{idx}. {sentence}")

else:
    print("No Wikipedia page found for the main topic related to the claim.")

# Perform fact-checking using the claim as input
results = fact_checking_pipeline(claim, candidate_labels)

# Print out the fact-checking results
print("\nFact-checking Results:")
for label, score in zip(results["labels"], results["scores"]):
    print(f"{label}: {score:.2f}")


"""
CSV Handler - Search and match creators from CSV file
"""

import csv
import logging
from typing import Optional, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def search_model_in_csv(creator_name: str, csv_path: str = 'onlyfans_models.csv') -> Optional[Tuple[str, str, float]]:
    """
    Search for a creator in the CSV file.
    Returns (matched_name, url, similarity_score) or None
    """
    try:
        best_match = None
        best_score = 0.0
        creator_name_lower = creator_name.lower()
        
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                model_name = row['model_name']
                profile_link = row['profile_link']
                
                # Check for exact match first
                if creator_name_lower == model_name.lower():
                    return (model_name, profile_link, 1.0)
                
                # Check if creator name is in model name (handles aliases)
                if creator_name_lower in model_name.lower():
                    score = 0.9
                    if score > best_score:
                        best_score = score
                        best_match = (model_name, profile_link, score)
                
                # Calculate similarity using SequenceMatcher
                similarity = SequenceMatcher(None, creator_name_lower, model_name.lower()).ratio()
                if similarity > best_score:
                    best_score = similarity
                    best_match = (model_name, profile_link, similarity)
        
        # Only return matches with at least 60% similarity
        if best_match and best_score >= 0.6:
            return best_match
            
        return None
        
    except Exception as e:
        logger.error(f"Error searching CSV: {e}")
        return None

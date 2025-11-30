"""
CSV Handler - Search and match creators from CSV file with advanced similarity algorithms
"""

import csv
import re
import logging
from typing import Optional, Tuple, List, Set
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class SimilarityCalculator:
    """Advanced similarity calculator using multiple algorithms."""
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalize text for better matching:
        - Convert to lowercase
        - Remove special characters except spaces
        - Normalize whitespace
        - Remove common filler words
        """
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters but keep spaces
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        # Remove common filler words that don't affect identity
        filler_words = {'the', 'a', 'an', 'of', 'and', 'or', 'onlyfans', 'only', 'fans', 'official'}
        words = text.split()
        words = [w for w in words if w not in filler_words]
        
        return ' '.join(words)
    
    @staticmethod
    def extract_tokens(text: str) -> Set[str]:
        """Extract meaningful tokens from text."""
        normalized = SimilarityCalculator.normalize_text(text)
        tokens = set(normalized.split())
        
        # Also add bigrams for better matching
        words = normalized.split()
        for i in range(len(words) - 1):
            tokens.add(f"{words[i]} {words[i+1]}")
        
        return tokens
    
    @staticmethod
    def levenshtein_distance(s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return SimilarityCalculator.levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # Cost of insertions, deletions, or substitutions
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    @staticmethod
    def jaro_winkler_similarity(s1: str, s2: str) -> float:
        """
        Calculate Jaro-Winkler similarity (good for names and short strings).
        Returns a value between 0 and 1.
        """
        # If strings are identical
        if s1 == s2:
            return 1.0
        
        # Get lengths
        len1, len2 = len(s1), len(s2)
        
        # Maximum allowed distance
        max_dist = max(len1, len2) // 2 - 1
        if max_dist < 0:
            max_dist = 0
        
        # Count matches
        matches = 0
        s1_matches = [False] * len1
        s2_matches = [False] * len2
        
        for i in range(len1):
            start = max(0, i - max_dist)
            end = min(i + max_dist + 1, len2)
            
            for j in range(start, end):
                if s2_matches[j] or s1[i] != s2[j]:
                    continue
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break
        
        if matches == 0:
            return 0.0
        
        # Count transpositions
        transpositions = 0
        k = 0
        for i in range(len1):
            if not s1_matches[i]:
                continue
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1
        
        # Calculate Jaro similarity
        jaro = (matches / len1 + matches / len2 + (matches - transpositions / 2) / matches) / 3
        
        # Calculate Jaro-Winkler similarity with prefix bonus
        prefix_len = 0
        for i in range(min(len1, len2, 4)):  # Max prefix length of 4
            if s1[i] == s2[i]:
                prefix_len += 1
            else:
                break
        
        jaro_winkler = jaro + (prefix_len * 0.1 * (1 - jaro))
        
        return jaro_winkler
    
    @staticmethod
    def token_similarity(s1: str, s2: str) -> float:
        """Calculate similarity based on token overlap (good for multi-word names)."""
        tokens1 = SimilarityCalculator.extract_tokens(s1)
        tokens2 = SimilarityCalculator.extract_tokens(s2)
        
        if not tokens1 or not tokens2:
            return 0.0
        
        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        
        # Jaccard similarity
        jaccard = len(intersection) / len(union) if union else 0.0
        
        # Also consider subset matching (one name is subset of another)
        subset_score = 0.0
        if tokens1.issubset(tokens2) or tokens2.issubset(tokens1):
            subset_score = 0.3
        
        return min(jaccard + subset_score, 1.0)
    
    @staticmethod
    def substring_similarity(s1: str, s2: str) -> float:
        """Calculate similarity based on substring matching."""
        s1_norm = SimilarityCalculator.normalize_text(s1)
        s2_norm = SimilarityCalculator.normalize_text(s2)
        
        # Check if one is a substring of the other
        if s1_norm in s2_norm:
            return 0.85 + (0.15 * (len(s1_norm) / len(s2_norm)))
        elif s2_norm in s1_norm:
            return 0.85 + (0.15 * (len(s2_norm) / len(s1_norm)))
        
        # Check for partial substring matches
        shorter, longer = (s1_norm, s2_norm) if len(s1_norm) < len(s2_norm) else (s2_norm, s1_norm)
        
        # Find longest common substring
        m, n = len(shorter), len(longer)
        max_len = 0
        
        for i in range(m):
            for j in range(n):
                k = 0
                while i + k < m and j + k < n and shorter[i + k] == longer[j + k]:
                    k += 1
                max_len = max(max_len, k)
        
        if max_len >= 3:  # At least 3 characters match
            return 0.6 + (0.3 * (max_len / len(shorter)))
        
        return 0.0
    
    @staticmethod
    def calculate_composite_similarity(query: str, target: str) -> float:
        """
        Calculate composite similarity using multiple algorithms with weighted scoring.
        Returns a score between 0 and 1.
        """
        # Normalize both strings for comparison
        query_norm = SimilarityCalculator.normalize_text(query)
        target_norm = SimilarityCalculator.normalize_text(target)
        
        # Exact match (after normalization)
        if query_norm == target_norm:
            return 1.0
        
        # Calculate different similarity metrics
        
        # 1. Sequence Matcher (standard library, fast)
        seq_sim = SequenceMatcher(None, query_norm, target_norm).ratio()
        
        # 2. Levenshtein distance normalized
        lev_dist = SimilarityCalculator.levenshtein_distance(query_norm, target_norm)
        max_len = max(len(query_norm), len(target_norm))
        lev_sim = 1 - (lev_dist / max_len) if max_len > 0 else 0.0
        
        # 3. Jaro-Winkler similarity (good for names)
        jaro_sim = SimilarityCalculator.jaro_winkler_similarity(query_norm, target_norm)
        
        # 4. Token-based similarity (good for multi-word names)
        token_sim = SimilarityCalculator.token_similarity(query, target)
        
        # 5. Substring similarity
        substr_sim = SimilarityCalculator.substring_similarity(query, target)
        
        # Weighted combination (tuned for name matching)
        weights = {
            'sequence': 0.20,
            'levenshtein': 0.20,
            'jaro_winkler': 0.25,
            'token': 0.20,
            'substring': 0.15
        }
        
        composite_score = (
            weights['sequence'] * seq_sim +
            weights['levenshtein'] * lev_sim +
            weights['jaro_winkler'] * jaro_sim +
            weights['token'] * token_sim +
            weights['substring'] * substr_sim
        )
        
        # Apply bonus for very short exact matches within longer names
        if len(query_norm) >= 3 and query_norm in target_norm.split():
            composite_score = max(composite_score, 0.85)
        
        return min(composite_score, 1.0)


def search_model_in_csv(creator_name: str, csv_path: str = 'onlyfans_models.csv') -> Optional[Tuple[str, str, float]]:
    """
    Search for a creator in the CSV file using advanced similarity algorithms.
    Returns (matched_name, url, similarity_score) or None
    """
    try:
        best_match = None
        best_score = 0.0
        
        calculator = SimilarityCalculator()
        
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                model_name = row['model_name']
                profile_link = row['profile_link']
                
                # Calculate composite similarity
                similarity = calculator.calculate_composite_similarity(creator_name, model_name)
                
                # Exact match detection (after normalization)
                if similarity >= 0.99:
                    logger.info(f"Exact match found: '{creator_name}' -> '{model_name}' (score: {similarity:.3f})")
                    return (model_name, profile_link, 1.0)
                
                if similarity > best_score:
                    best_score = similarity
                    best_match = (model_name, profile_link, similarity)
        
        # Only return matches with at least 50% similarity
        if best_match and best_score >= 0.5:
            logger.info(f"Best match for '{creator_name}': '{best_match[0]}' (score: {best_score:.3f})")
            return best_match
        
        logger.info(f"No sufficient match found for '{creator_name}' (best score: {best_score:.3f})")
        return None
        
    except Exception as e:
        logger.error(f"Error searching CSV: {e}")
        return None


def search_multiple_models_in_csv(creator_name: str, csv_path: str = 'onlyfans_models.csv', max_results: int = 5) -> List[Tuple[str, str, float]]:
    """
    Search for multiple potential matches in the CSV file using advanced similarity.
    Returns list of (matched_name, url, similarity_score) tuples, sorted by similarity
    """
    try:
        matches = []
        calculator = SimilarityCalculator()
        
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                model_name = row['model_name']
                profile_link = row['profile_link']
                
                # Calculate composite similarity
                similarity = calculator.calculate_composite_similarity(creator_name, model_name)
                
                # Exact match - return immediately
                if similarity >= 0.99:
                    logger.info(f"Exact match found: '{creator_name}' -> '{model_name}'")
                    return [(model_name, profile_link, 1.0)]
                
                # Include matches with at least 50% similarity for multiple results
                if similarity >= 0.5:
                    matches.append((model_name, profile_link, similarity))
        
        # Sort by similarity (highest first) and return top results
        matches.sort(key=lambda x: x[2], reverse=True)
        
        if matches:
            logger.info(f"Found {len(matches)} matches for '{creator_name}':")
            for i, (name, _, score) in enumerate(matches[:max_results], 1):
                logger.info(f"  {i}. '{name}' (score: {score:.3f})")
        
        return matches[:max_results]
        
    except Exception as e:
        logger.error(f"Error searching CSV for multiple matches: {e}")
        return []

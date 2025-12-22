"""
CSV Handler - Search and match creators from CSV file with advanced similarity algorithms
"""

import csv
import re
import logging
from typing import Optional, Tuple, List, Set
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor
import asyncio
from datetime import datetime, timedelta

# Import rapidfuzz for faster fuzzy matching
try:
    from rapidfuzz import fuzz, process
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logging.warning("rapidfuzz not available, falling back to difflib")

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound CSV operations
# Increased workers from 4 to 8 for better performance
_csv_executor = ThreadPoolExecutor(max_workers=8)

# In-memory cache for CSV data
_csv_cache = {
    'data': None,
    'last_loaded': None,
    'file_path': None
}
_cache_ttl = timedelta(minutes=5)  # Cache CSV for 5 minutes


def _load_csv_to_memory(csv_path: str) -> List[dict]:
    """Load CSV file into memory for faster access."""
    global _csv_cache
    
    # Check if cache is valid
    now = datetime.now()
    if (_csv_cache['data'] is not None and 
        _csv_cache['file_path'] == csv_path and
        _csv_cache['last_loaded'] is not None and
        now - _csv_cache['last_loaded'] < _cache_ttl):
        logger.debug(f"Using cached CSV data ({len(_csv_cache['data'])} rows)")
        return _csv_cache['data']
    
    # Load CSV into memory
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            data = list(reader)
        
        # Update cache
        _csv_cache['data'] = data
        _csv_cache['last_loaded'] = now
        _csv_cache['file_path'] = csv_path
        
        logger.info(f"Loaded {len(data)} rows from CSV into memory cache")
        return data
    except Exception as e:
        logger.error(f"Error loading CSV to memory: {e}")
        return []


def preload_csv_cache(csv_path: str = 'onlyfans_models.csv'):
    """Preload CSV data into cache at startup for instant access."""
    try:
        data = _load_csv_to_memory(csv_path)
        logger.info(f"Preloaded {len(data)} models into CSV cache")
        return len(data)
    except Exception as e:
        logger.error(f"Failed to preload CSV cache: {e}")
        return 0


def clear_csv_cache():
    """Clear the CSV cache (useful for testing or after CSV updates)."""
    global _csv_cache
    _csv_cache['data'] = None
    _csv_cache['last_loaded'] = None
    _csv_cache['file_path'] = None
    logger.info("CSV cache cleared")


class SimilarityCalculator:
    """Advanced similarity calculator using multiple algorithms with caching."""
    
    # Class-level cache for similarity calculations
    _similarity_cache = {}
    _cache_max_size = 1000
    
    @staticmethod
    def _get_cache_key(s1: str, s2: str) -> str:
        """Generate cache key for similarity calculation."""
        # Sort to ensure (a,b) and (b,a) produce same key
        sorted_pair = tuple(sorted([s1.lower(), s2.lower()]))
        return f"{sorted_pair[0]}||{sorted_pair[1]}"
    
    @staticmethod
    def _clean_cache():
        """Clean cache if it exceeds max size."""
        if len(SimilarityCalculator._similarity_cache) > SimilarityCalculator._cache_max_size:
            # Remove oldest 20% of entries
            remove_count = SimilarityCalculator._cache_max_size // 5
            keys_to_remove = list(SimilarityCalculator._similarity_cache.keys())[:remove_count]
            for key in keys_to_remove:
                del SimilarityCalculator._similarity_cache[key]
    
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
        Uses caching for repeated calculations.
        Returns a score between 0 and 1.
        """
        # Check cache first
        cache_key = SimilarityCalculator._get_cache_key(query, target)
        if cache_key in SimilarityCalculator._similarity_cache:
            return SimilarityCalculator._similarity_cache[cache_key]
        
        # Normalize both strings for comparison
        query_norm = SimilarityCalculator.normalize_text(query)
        target_norm = SimilarityCalculator.normalize_text(target)
        
        # Exact match (after normalization)
        if query_norm == target_norm:
            SimilarityCalculator._similarity_cache[cache_key] = 1.0
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
        
        result = min(composite_score, 1.0)
        
        # Cache the result
        SimilarityCalculator._similarity_cache[cache_key] = result
        SimilarityCalculator._clean_cache()
        
        return result


def search_model_in_csv(creator_name: str, csv_path: str = 'onlyfans_models.csv') -> Optional[Tuple[str, str, float]]:
    """
    Search for a creator in the CSV file using advanced similarity algorithms.
    Handles multi-alias names (separated by |) by checking each alias individually.
    Uses in-memory cache for faster access.
    Returns (matched_name, url, similarity_score) or None
    """
    try:
        best_match = None
        best_score = 0.0
        
        calculator = SimilarityCalculator()
        
        # Load CSV from cache
        rows = _load_csv_to_memory(csv_path)
        
        for row in rows:
            model_name = row['model_name']
            profile_link = row['profile_link']
            
            # Split by '|' to get individual aliases
            aliases = [alias.strip() for alias in model_name.split('|')]
            
            # Check similarity against each alias
            max_alias_similarity = 0.0
            for alias in aliases:
                if not alias:  # Skip empty aliases
                    continue
                
                similarity = calculator.calculate_composite_similarity(creator_name, alias)
                max_alias_similarity = max(max_alias_similarity, similarity)
                
                # Exact match detection (after normalization)
                if similarity >= 0.99:
                    logger.info(f"Exact match found: '{creator_name}' -> '{alias}' in '{model_name}' (score: {similarity:.3f})")
                    return (model_name, profile_link, 1.0)
            
            # Use the best alias match for this row
            if max_alias_similarity > best_score:
                best_score = max_alias_similarity
                best_match = (model_name, profile_link, max_alias_similarity)
        
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
    Handles multi-alias names (separated by |) by checking each alias individually.
    Uses in-memory cache for faster access.
    Returns list of (matched_name, url, similarity_score) tuples, sorted by similarity
    """
    try:
        matches = []
        calculator = SimilarityCalculator()
        
        # Load CSV from cache
        rows = _load_csv_to_memory(csv_path)
        
        for row in rows:
            model_name = row['model_name']
            profile_link = row['profile_link']
            
            # Split by '|' to get individual aliases
            aliases = [alias.strip() for alias in model_name.split('|')]
            
            # Check similarity against each alias
            max_alias_similarity = 0.0
            for alias in aliases:
                if not alias:  # Skip empty aliases
                    continue
                
                similarity = calculator.calculate_composite_similarity(creator_name, alias)
                max_alias_similarity = max(max_alias_similarity, similarity)
                
                # Exact match - return immediately
                if similarity >= 0.99:
                    logger.info(f"Exact match found: '{creator_name}' -> '{alias}' in '{model_name}'")
                    return [(model_name, profile_link, 1.0)]
            
            # Use the best alias match for this row
            if max_alias_similarity >= 0.5:
                matches.append((model_name, profile_link, max_alias_similarity))
        
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


def _process_csv_chunk(chunk: List[dict], creator_name: str, calculator: SimilarityCalculator) -> List[Tuple[str, str, float]]:
    """Process a chunk of CSV rows in parallel."""
    matches = []
    
    for row in chunk:
        model_name = row['model_name']
        profile_link = row['profile_link']
        
        # Split by '|' to get individual aliases
        aliases = [alias.strip() for alias in model_name.split('|')]
        
        # Check similarity against each alias
        max_alias_similarity = 0.0
        for alias in aliases:
            if not alias:
                continue
            
            similarity = calculator.calculate_composite_similarity(creator_name, alias)
            max_alias_similarity = max(max_alias_similarity, similarity)
            
            # Exact match
            if similarity >= 0.99:
                return [(model_name, profile_link, 1.0, True)]  # True flag indicates exact match
        
        # Use the best alias match for this row
        if max_alias_similarity >= 0.5:
            matches.append((model_name, profile_link, max_alias_similarity, False))
    
    return matches


async def search_multiple_models_in_csv_parallel(creator_name: str, csv_path: str = 'onlyfans_models.csv', max_results: int = 5) -> List[Tuple[str, str, float]]:
    """
    Search for multiple potential matches in CSV using parallel processing.
    Much faster for large CSV files. Uses in-memory cache.
    Returns list of (matched_name, url, similarity_score) tuples, sorted by similarity
    """
    try:
        calculator = SimilarityCalculator()
        
        # Load CSV from cache (much faster)
        all_rows = _load_csv_to_memory(csv_path)
        
        # If dataset is small, use sequential processing
        if len(all_rows) < 1000:
            return search_multiple_models_in_csv(creator_name, csv_path, max_results)
        
        # Split into chunks for parallel processing
        chunk_size = max(100, len(all_rows) // 4)  # 4 workers
        chunks = [all_rows[i:i + chunk_size] for i in range(0, len(all_rows), chunk_size)]
        
        # Process chunks in parallel using thread pool
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(_csv_executor, _process_csv_chunk, chunk, creator_name, calculator)
            for chunk in chunks
        ]
        
        # Gather results from all chunks
        chunk_results = await asyncio.gather(*tasks)
        
        # Flatten results and check for exact matches
        matches = []
        for chunk_matches in chunk_results:
            for match in chunk_matches:
                # Check if exact match found (4th element is True)
                if len(match) == 4 and match[3]:
                    # Exact match found, return immediately
                    logger.info(f"Exact match found: '{creator_name}' -> '{match[0]}'")
                    return [(match[0], match[1], match[2])]
                matches.append((match[0], match[1], match[2]))
        
        # Sort by similarity (highest first) and return top results
        matches.sort(key=lambda x: x[2], reverse=True)
        
        if matches:
            logger.info(f"Found {len(matches)} matches for '{creator_name}' (parallel search):")
            for i, (name, _, score) in enumerate(matches[:max_results], 1):
                logger.info(f"  {i}. '{name}' (score: {score:.3f})")
        
        return matches[:max_results]
        
    except Exception as e:
        logger.error(f"Error in parallel CSV search: {e}")
        # Fallback to sequential search
        return search_multiple_models_in_csv(creator_name, csv_path, max_results)


async def search_csv_with_rapidfuzz(creator_name: str, csv_path: str = 'onlyfans_models.csv', max_results: int = 5) -> List[Tuple[str, str, float]]:
    """
    Fast CSV search using rapidfuzz library.
    Provides better performance for large datasets.
    Returns list of (matched_name, url, similarity_score) tuples, sorted by similarity
    """
    if not RAPIDFUZZ_AVAILABLE:
        logger.warning("rapidfuzz not available, using standard search")
        return await search_multiple_models_in_csv_parallel(creator_name, csv_path, max_results)
    
    try:
        # Load CSV from cache
        all_rows = _load_csv_to_memory(csv_path)
        
        if not all_rows:
            logger.warning(f"No data found in CSV: {csv_path}")
            return []
        
        # Normalize query
        from scrapers.fuzzy_search import FuzzySearchEngine
        engine = FuzzySearchEngine()
        query_norm = engine.normalize_name(creator_name)
        
        # Prepare data for fuzzy matching
        # For each row, extract all aliases and create tuples of (normalized_alias, original_row)
        candidates = []
        for row in all_rows:
            model_name = row['model_name']
            profile_link = row['profile_link']
            
            # Split by '|' to get individual aliases
            aliases = [alias.strip() for alias in model_name.split('|')]
            
            for alias in aliases:
                if not alias:
                    continue
                alias_norm = engine.normalize_name(alias)
                candidates.append((alias_norm, model_name, profile_link, alias))
        
        logger.info(f"Searching {len(candidates)} aliases with rapidfuzz for '{creator_name}'")
        
        # Use rapidfuzz's process.extract for fast matching
        matches = process.extract(
            query_norm,
            [c[0] for c in candidates],
            scorer=fuzz.WRatio,
            limit=max_results * 2,  # Get more to deduplicate
            score_cutoff=50  # Minimum 50% similarity
        )
        
        # Map back to original data and deduplicate by profile_link
        seen_urls = set()
        results = []
        
        for normalized_match, score, idx in matches:
            original_name = candidates[idx][1]
            profile_link = candidates[idx][2]
            matched_alias = candidates[idx][3]
            
            # Skip duplicates
            if profile_link in seen_urls:
                continue
            
            seen_urls.add(profile_link)
            # Convert score from 0-100 to 0-1 for consistency
            results.append((original_name, profile_link, score / 100.0))
            
            if len(results) >= max_results:
                break
        
        if results:
            logger.info(f"Rapidfuzz found {len(results)} matches for '{creator_name}':")
            for i, (name, _, score) in enumerate(results, 1):
                logger.info(f"  {i}. '{name}' (score: {score:.3f})")
        else:
            logger.info(f"No rapidfuzz matches found for '{creator_name}'")
        
        return results
        
    except Exception as e:
        logger.error(f"Error in rapidfuzz CSV search: {e}")
        # Fallback to standard search
        return await search_multiple_models_in_csv_parallel(creator_name, csv_path, max_results)


def get_all_creators_from_csv(csv_path: str = 'onlyfans_models.csv', max_results: Optional[int] = None) -> List[dict]:
    """
    Get all creators from CSV file.
    
    Args:
        csv_path: Path to the CSV file
        max_results: Maximum number of results to return (None for all)
        
    Returns:
        List of dicts with 'name' and 'url' keys
    """
    try:
        csv_data = _load_csv_to_memory(csv_path)
        
        if not csv_data:
            logger.warning("CSV data is empty")
            return []
        
        results = []
        for row in csv_data:
            # Support both naming conventions: 'Name'/'Profile Link' and 'model_name'/'profile_link'
            name = row.get('Name', row.get('model_name', '')).strip()
            url = row.get('Profile Link', row.get('profile_link', '')).strip()
            
            if name and url:
                results.append({'name': name, 'url': url})
            
            if max_results and len(results) >= max_results:
                break
        
        logger.info(f"Retrieved {len(results)} creators from CSV")
        return results
        
    except Exception as e:
        logger.error(f"Error getting all creators from CSV: {e}")
        return []

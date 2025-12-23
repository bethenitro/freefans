"""
Enhanced Fuzzy Search Module - Advanced fuzzy matching for SimpCity search results
Uses rapidfuzz library for high-performance fuzzy string matching
"""

import logging
import re
from typing import List, Dict, Tuple, Optional
from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

logger = logging.getLogger(__name__)


class FuzzySearchEngine:
    """
    Advanced fuzzy search engine optimized for creator name matching.
    Uses multiple scoring strategies to find the best matches.
    """
    
    def __init__(self, min_score: int = 60):
        """
        Initialize fuzzy search engine.
        
        Args:
            min_score: Minimum fuzzy match score (0-100) to consider a match
        """
        self.min_score = min_score
        self._cache = {}
    
    @staticmethod
    def normalize_name(name: str) -> str:
        """
        Normalize creator name for better matching.
        Removes platform tags, special characters, and extra whitespace.
        
        Args:
            name: Raw name string
            
        Returns:
            Normalized name
        """
        # Convert to lowercase
        name = name.lower()
        
        # Remove common platform and category labels
        labels_to_remove = [
            'onlyfans', 'fansly', 'instagram', 'twitter', 'tiktok', 'snapchat',
            'request', 'latina', 'asian', 'ebony', 'bbw', 'milf', 'teen',
            'amateur', 'professional', 'leaked', 'premium', 'vip', 'free',
            'model', 'creator', 'influencer', 'cosplay', 'gamer', 'fitness',
            'petite', 'curvy', 'slim', 'thick', 'blonde', 'brunette', 'redhead',
            'tattooed', 'natural', 'enhanced', 'solo', 'couple', 'group',
            'exclusive', 'official', 'real', 'verified', 'new', 'hot', 'sexy'
        ]
        
        # Remove labels with word boundaries
        for label in labels_to_remove:
            name = re.sub(r'\b' + re.escape(label) + r'\b', '', name, flags=re.IGNORECASE)
        
        # Remove special characters but keep spaces and hyphens
        name = re.sub(r'[^a-z0-9\s\-]', ' ', name)
        
        # Normalize whitespace
        name = re.sub(r'\s+', ' ', name)
        name = name.strip()
        
        return name
    
    @staticmethod
    def extract_aliases(name: str) -> List[str]:
        """
        Extract possible name variations/aliases from a name string.
        Handles formats like "Name1 / Name2 | Name3" or "Name (Alias)"
        
        Args:
            name: Name string that may contain multiple aliases
            
        Returns:
            List of extracted aliases
        """
        aliases = []
        
        # Split by common separators
        parts = re.split(r'[/|]', name)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Extract text in parentheses as separate alias
            paren_matches = re.findall(r'\(([^)]+)\)', part)
            for match in paren_matches:
                match = match.strip()
                if match and len(match) > 2:
                    aliases.append(match)
            
            # Remove parentheses from main part
            main_part = re.sub(r'\([^)]*\)', '', part).strip()
            if main_part and len(main_part) > 2:
                aliases.append(main_part)
        
        # Deduplicate while preserving order
        seen = set()
        unique_aliases = []
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower not in seen:
                seen.add(alias_lower)
                unique_aliases.append(alias)
        
        return unique_aliases if unique_aliases else [name]
    
    def calculate_fuzzy_score(self, query: str, target: str, use_partial: bool = True) -> Dict[str, float]:
        """
        Calculate multiple fuzzy match scores for two strings.
        
        Args:
            query: Search query
            target: Target string to match against
            use_partial: Whether to include partial matching scores
            
        Returns:
            Dictionary with different scoring metrics
        """
        query_norm = self.normalize_name(query)
        target_norm = self.normalize_name(target)
        
        scores = {
            'ratio': fuzz.ratio(query_norm, target_norm),
            'partial_ratio': fuzz.partial_ratio(query_norm, target_norm) if use_partial else 0,
            'token_sort_ratio': fuzz.token_sort_ratio(query_norm, target_norm),
            'token_set_ratio': fuzz.token_set_ratio(query_norm, target_norm),
            'weighted_ratio': fuzz.WRatio(query_norm, target_norm),
        }
        
        # Calculate a composite score with weights optimized for name matching
        weights = {
            'ratio': 0.20,
            'partial_ratio': 0.15,
            'token_sort_ratio': 0.25,
            'token_set_ratio': 0.20,
            'weighted_ratio': 0.20,
        }
        
        composite = sum(scores[key] * weights[key] for key in weights)
        scores['composite'] = composite
        
        # Bonus for exact substring match
        if query_norm in target_norm or target_norm in query_norm:
            scores['substring_bonus'] = min(15, len(query_norm) * 2)
            scores['composite'] = min(100, scores['composite'] + scores['substring_bonus'])
        else:
            scores['substring_bonus'] = 0
        
        return scores
    
    def find_best_matches(
        self,
        query: str,
        candidates: List[Dict],
        limit: int = 10,
        score_cutoff: Optional[int] = None
    ) -> List[Tuple[Dict, float, Dict]]:
        """
        Find best fuzzy matches from a list of candidates.
        
        Args:
            query: Search query
            candidates: List of candidate dictionaries with 'title' or 'name' field
            limit: Maximum number of results to return
            score_cutoff: Minimum score threshold (uses self.min_score if None)
            
        Returns:
            List of tuples: (candidate_dict, score, detailed_scores)
        """
        if score_cutoff is None:
            score_cutoff = self.min_score
        
        results = []
        query_norm = self.normalize_name(query)
        
        for candidate in candidates:
            # Get the name from candidate (support both 'title' and 'name' fields)
            candidate_name = candidate.get('title') or candidate.get('name', '')
            
            if not candidate_name:
                continue
            
            # Extract and check all aliases
            aliases = self.extract_aliases(candidate_name)
            best_score = 0
            best_detailed_scores = None
            
            for alias in aliases:
                detailed_scores = self.calculate_fuzzy_score(query, alias)
                composite_score = detailed_scores['composite']
                
                if composite_score > best_score:
                    best_score = composite_score
                    best_detailed_scores = detailed_scores
            
            # Add to results if above threshold
            if best_score >= score_cutoff:
                results.append((candidate, best_score, best_detailed_scores))
        
        # Sort by score (highest first)
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:limit]
    
    def rank_search_results(
        self,
        query: str,
        search_results: List[Dict],
        limit: int = 10,
        boost_factors: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Rank search results using fuzzy matching with optional boost factors.
        
        Args:
            query: Original search query
            search_results: List of search result dictionaries from SimpCity
            limit: Maximum number of results to return
            boost_factors: Optional dict with boost multipliers for specific fields
                          e.g., {'replies': 0.01, 'has_onlyfans_label': 10}
            
        Returns:
            Ranked and filtered list of search results with 'fuzzy_score' added
        """
        if not boost_factors:
            boost_factors = {
                'replies': 0.01,  # Small boost per reply
                'has_onlyfans_label': 5,  # Moderate boost for OnlyFans label
            }
        
        # Find best matches
        matches = self.find_best_matches(query, search_results, limit=len(search_results))
        
        ranked_results = []
        for candidate, base_score, detailed_scores in matches:
            # Start with fuzzy match score
            final_score = base_score
            
            # Apply boost factors
            if 'replies' in candidate and 'replies' in boost_factors:
                reply_boost = min(candidate['replies'] * boost_factors['replies'], 10)
                final_score += reply_boost
            
            if candidate.get('has_onlyfans_label') and 'has_onlyfans_label' in boost_factors:
                final_score += boost_factors['has_onlyfans_label']
            
            # Ensure score doesn't exceed 100
            final_score = min(final_score, 100)
            
            # Add scoring information to result
            result = candidate.copy()
            result['fuzzy_score'] = final_score
            result['base_fuzzy_score'] = base_score
            result['fuzzy_details'] = detailed_scores
            
            ranked_results.append(result)
        
        # Sort by final score
        ranked_results.sort(key=lambda x: x['fuzzy_score'], reverse=True)
        
        # Log top results
        if ranked_results:
            logger.info(f"Fuzzy search ranked {len(ranked_results)} results for '{query}':")
            for i, result in enumerate(ranked_results[:5], 1):
                logger.info(
                    f"  {i}. '{result.get('title', 'Unknown')}' "
                    f"(score: {result['fuzzy_score']:.1f}, base: {result['base_fuzzy_score']:.1f})"
                )
        
        return ranked_results[:limit]
    
    def get_best_match(
        self,
        query: str,
        candidates: List[Dict],
        threshold: Optional[int] = None
    ) -> Optional[Tuple[Dict, float]]:
        """
        Get single best match from candidates.
        
        Args:
            query: Search query
            candidates: List of candidate dictionaries
            threshold: Minimum score threshold (uses self.min_score if None)
            
        Returns:
            Tuple of (best_match_dict, score) or None if no match above threshold
        """
        if threshold is None:
            threshold = self.min_score
        
        matches = self.find_best_matches(query, candidates, limit=1, score_cutoff=threshold)
        
        if matches:
            best_match, score, _ = matches[0]
            logger.info(f"Best fuzzy match for '{query}': '{best_match.get('title', 'Unknown')}' (score: {score:.1f})")
            return (best_match, score)
        
        return None
    
    def filter_by_query(
        self,
        query: str,
        candidates: List[Dict],
        min_score: Optional[int] = None
    ) -> List[Dict]:
        """
        Filter candidates to only those matching the query above threshold.
        
        Args:
            query: Search query
            candidates: List of candidate dictionaries
            min_score: Minimum score threshold (uses self.min_score if None)
            
        Returns:
            Filtered list of candidates
        """
        if min_score is None:
            min_score = self.min_score
        
        matches = self.find_best_matches(
            query,
            candidates,
            limit=len(candidates),
            score_cutoff=min_score
        )
        
        return [match[0] for match in matches]


# Convenience function for quick fuzzy matching
def fuzzy_match_names(query: str, targets: List[str], limit: int = 5, score_cutoff: int = 60) -> List[Tuple[str, float]]:
    """
    Quick fuzzy match function for simple string matching.
    
    Args:
        query: Search query
        targets: List of target strings
        limit: Maximum results
        score_cutoff: Minimum score
        
    Returns:
        List of (matched_string, score) tuples
    """
    engine = FuzzySearchEngine(min_score=score_cutoff)
    query_norm = engine.normalize_name(query)
    
    # Use rapidfuzz's process.extract for fast matching
    matches = process.extract(
        query_norm,
        [engine.normalize_name(t) for t in targets],
        scorer=fuzz.WRatio,
        limit=limit,
        score_cutoff=score_cutoff
    )
    
    # Map back to original targets
    results = []
    for normalized_target, score, idx in matches:
        results.append((targets[idx], score))
    
    return results

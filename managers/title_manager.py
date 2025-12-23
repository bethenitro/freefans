"""
Title Manager - Manages worker-submitted video titles and admin approvals
"""

import csv
import os
import logging
from typing import List, Optional, Dict
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


class TitleManager:
    """Manages video title submissions and approvals."""
    
    def __init__(self, submissions_dir: str = 'data/title_submissions'):
        """Initialize title manager."""
        self.submissions_dir = submissions_dir
        self.pending_file = os.path.join(submissions_dir, 'pending_titles.csv')
        self.approved_file = os.path.join(submissions_dir, 'approved_titles.csv')
        self.rejected_file = os.path.join(submissions_dir, 'rejected_titles.csv')
        self.lock = threading.Lock()
        self._init_storage()
    
    def _init_storage(self):
        """Initialize storage directory and CSV files."""
        os.makedirs(self.submissions_dir, exist_ok=True)
        
        # Initialize pending titles CSV
        if not os.path.exists(self.pending_file):
            with open(self.pending_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'submission_id', 'timestamp', 'worker_id', 'worker_username',
                    'video_url', 'creator_name', 'suggested_title', 'status'
                ])
        
        # Initialize approved titles CSV
        if not os.path.exists(self.approved_file):
            with open(self.approved_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'submission_id', 'timestamp', 'worker_id', 'worker_username',
                    'video_url', 'creator_name', 'suggested_title', 
                    'approved_by', 'approved_at'
                ])
        
        # Initialize rejected titles CSV
        if not os.path.exists(self.rejected_file):
            with open(self.rejected_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'submission_id', 'timestamp', 'worker_id', 'worker_username',
                    'video_url', 'creator_name', 'suggested_title',
                    'rejected_by', 'rejected_at', 'reason'
                ])
    
    def submit_title(self, worker_id: int, worker_username: str, 
                    video_url: str, creator_name: str, title: str) -> str:
        """
        Submit a new title suggestion from a worker.
        
        Returns:
            submission_id: Unique ID for this submission
        """
        with self.lock:
            timestamp = datetime.now()
            submission_id = f"TS-{timestamp.strftime('%Y%m%d%H%M%S')}-{worker_id}"
            
            with open(self.pending_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    submission_id,
                    timestamp.isoformat(),
                    worker_id,
                    worker_username or 'Unknown',
                    video_url,
                    creator_name,
                    title,
                    'pending'
                ])
            
            logger.info(f"Title submission {submission_id} from worker {worker_id}")
            return submission_id
    
    def get_pending_titles(self, worker_id: Optional[int] = None) -> List[Dict]:
        """
        Get all pending title submissions.
        
        Args:
            worker_id: If provided, filter by specific worker
            
        Returns:
            List of pending submissions
        """
        return self._get_pending_titles_internal(worker_id)
    
    def _get_pending_titles_internal(self, worker_id: Optional[int] = None) -> List[Dict]:
        """Internal method to get pending titles without acquiring lock."""
        pending = []
        
        if not os.path.exists(self.pending_file):
            return pending
        
        with open(self.pending_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if worker_id is None or int(row['worker_id']) == worker_id:
                    pending.append(row)
        
        return pending
    
    def approve_title(self, submission_id: str, admin_id: int) -> Optional[Dict]:
        """
        Approve a title submission.
        
        Returns:
            Dict with submission data if found, None otherwise
        """
        with self.lock:
            # Find and remove from pending
            submission = self._move_submission(
                submission_id, 
                self.pending_file, 
                self.approved_file,
                admin_id=admin_id
            )
            
            if submission:
                logger.info(f"Title {submission_id} approved by admin {admin_id}")
            
            return submission
    
    def reject_title(self, submission_id: str, admin_id: int, reason: str = '') -> Optional[Dict]:
        """
        Reject a title submission.
        
        Returns:
            Dict with submission data if found, None otherwise
        """
        with self.lock:
            return self._reject_title_internal(submission_id, admin_id, reason)
    
    def _reject_title_internal(self, submission_id: str, admin_id: int, reason: str = '') -> Optional[Dict]:
        """Internal reject method without lock acquisition."""
        # Find and remove from pending
        submission = self._move_submission(
            submission_id,
            self.pending_file,
            self.rejected_file,
            admin_id=admin_id,
            reason=reason
        )
        
        if submission:
            logger.info(f"Title {submission_id} rejected by admin {admin_id}")
        
        return submission
    
    def _move_submission(self, submission_id: str, from_file: str, 
                        to_file: str, admin_id: int, reason: str = '') -> Optional[Dict]:
        """Move a submission from one file to another."""
        remaining_rows = []
        found_submission = None
        
        # Read all rows and find the submission
        with open(from_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            for row in reader:
                if row['submission_id'] == submission_id:
                    found_submission = row
                else:
                    remaining_rows.append(row)
        
        if not found_submission:
            return None
        
        # Write back remaining rows
        with open(from_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(remaining_rows)
        
        # Add to destination file
        timestamp = datetime.now().isoformat()
        
        if to_file == self.approved_file:
            with open(to_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    found_submission['submission_id'],
                    found_submission['timestamp'],
                    found_submission['worker_id'],
                    found_submission['worker_username'],
                    found_submission['video_url'],
                    found_submission['creator_name'],
                    found_submission['suggested_title'],
                    admin_id,
                    timestamp
                ])
        elif to_file == self.rejected_file:
            with open(to_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    found_submission['submission_id'],
                    found_submission['timestamp'],
                    found_submission['worker_id'],
                    found_submission['worker_username'],
                    found_submission['video_url'],
                    found_submission['creator_name'],
                    found_submission['suggested_title'],
                    admin_id,
                    timestamp,
                    reason
                ])
        
        return found_submission
    
    def bulk_approve_worker(self, worker_id: int, admin_id: int) -> List[Dict]:
        """
        Approve all pending submissions from a specific worker.
        
        Returns:
            List of approved submissions
        """
        with self.lock:
            pending = self.get_pending_titles(worker_id=worker_id)
            approved = []
            
            for submission in pending:
                result = self.approve_title(submission['submission_id'], admin_id)
                if result:
                    approved.append(result)
            
            logger.info(f"Bulk approved {len(approved)} titles from worker {worker_id}")
            return approved
    
    def bulk_reject_worker(self, worker_id: int, admin_id: int, reason: str = 'Bulk rejected') -> List[Dict]:
        """
        Reject all pending submissions from a specific worker.
        
        Returns:
            List of rejected submissions
        """
        with self.lock:
            pending = self._get_pending_titles_internal(worker_id=worker_id)
            rejected = []
            
            for submission in pending:
                result = self._reject_title_internal(submission['submission_id'], admin_id, reason)
                if result:
                    rejected.append(result)
            
            logger.info(f"Bulk rejected {len(rejected)} titles from worker {worker_id}")
            return rejected
    
    def get_worker_stats(self, worker_id: int) -> Dict:
        """Get statistics for a specific worker."""
        with self.lock:
            stats = {
                'pending': 0,
                'approved': 0,
                'rejected': 0,
                'total': 0
            }
            
            # Count pending
            pending = self._get_pending_titles_internal(worker_id=worker_id)
            stats['pending'] = len(pending)
            
            # Count approved
            if os.path.exists(self.approved_file):
                with open(self.approved_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if int(row['worker_id']) == worker_id:
                            stats['approved'] += 1
            
            # Count rejected
            if os.path.exists(self.rejected_file):
                with open(self.rejected_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if int(row['worker_id']) == worker_id:
                            stats['rejected'] += 1
            
            stats['total'] = stats['pending'] + stats['approved'] + stats['rejected']
            
            return stats


# Singleton instance
_title_manager = None


def get_title_manager() -> TitleManager:
    """Get singleton instance of TitleManager."""
    global _title_manager
    if _title_manager is None:
        _title_manager = TitleManager()
    return _title_manager

# Admin & Worker System Documentation

## Overview

The FreeFans Bot now includes a comprehensive admin and worker system for managing user requests and improving video titles through crowd-sourcing.

## System Components

### 1. Permissions Manager (`permissions_manager.py`)
- Manages admin and worker user IDs
- Stores permissions in `permissions_config.json`
- Thread-safe operations

### 2. Title Manager (`title_manager.py`)
- Handles video title submissions from workers
- Manages approval/rejection workflow
- Stores data in `title_submissions/` directory:
  - `pending_titles.csv` - Awaiting admin review
  - `approved_titles.csv` - Approved titles
  - `rejected_titles.csv` - Rejected titles

### 3. Request Manager (`request_manager.py`)
- Manages user requests for creators and content
- Stores data in `requests/` directory:
  - `creator_requests.csv` - Creator addition requests
  - `content_requests.csv` - Specific content requests

## Setup Instructions

### Adding Admins and Workers

Use the `manage_permissions.py` script to manage permissions from the backend:

```bash
# Add an admin
python manage_permissions.py add-admin 123456789

# Add a worker
python manage_permissions.py add-worker 987654321

# List all permissions
python manage_permissions.py list

# Remove permissions
python manage_permissions.py remove-admin 123456789
python manage_permissions.py remove-worker 987654321
```

**How to get a user's Telegram ID:**
1. Have the user send a message to the bot
2. Check the bot logs - the user ID is logged
3. Or use a Telegram bot like @userinfobot

## Admin Commands

### `/requests` - View Pending User Requests
Shows all pending creator and content requests from users.

**Example:**
```
/requests
```

### `/titles` - View Pending Title Submissions
Shows all pending video title submissions from workers.

**Example:**
```
/titles
```

### `/approve <submission_id>` - Approve a Title
Approves a worker's title submission and updates the cache.

**Example:**
```
/approve TS-20251223120000-123456789
```

### `/reject <submission_id> [reason]` - Reject a Title
Rejects a worker's title submission with optional reason.

**Example:**
```
/reject TS-20251223120000-123456789 Title too vague
```

### `/bulkapprove <worker_id>` - Bulk Approve Worker
Approves all pending titles from a specific worker at once.

**Example:**
```
/bulkapprove 987654321
```

### `/adminstats` - View System Statistics
Shows comprehensive statistics about the system.

**Example:**
```
/adminstats
```

## Worker Commands

### Submitting Titles

Workers submit titles by replying to video messages:

1. Find a video in the content library
2. Reply to that video message
3. Type your suggested title in the reply
4. Wait for admin approval

**Example:**
```
User sees video message with URL
Worker replies: "Hot Tub Stream - Bikini Try-On Haul"
```

### `/mystats` - View Personal Statistics
Shows worker's submission statistics including pending, approved, and rejected counts.

**Example:**
```
/mystats
```

### `/workerhelp` - Worker Guide
Shows detailed guide on how to submit good titles.

**Example:**
```
/workerhelp
```

## Title Submission Guidelines

### Good Titles ✅
- "Hot Tub Stream - Bikini Try-On Haul"
- "Beach Photoshoot Behind The Scenes"
- "Exclusive Private Show Highlights"
- "Yoga Session in Tight Leggings"

### Bad Titles ❌
- "video1"
- "untitled"
- "watch this"
- "!!MUST SEE!!"

### Best Practices
- Be descriptive and accurate
- Keep titles under 200 characters
- Include key details (location, activity, outfit, etc.)
- Avoid clickbait or misleading titles
- Use proper capitalization
- No excessive punctuation or emojis

## Workflow

### User Request Flow
1. User requests creator/content via menu buttons
2. Request saved to CSV with unique ID
3. Admin reviews with `/requests` command
4. Admin manually adds content (outside bot scope)

### Title Submission Flow
1. Worker replies to video with suggested title
2. Title saved as "pending" in `pending_titles.csv`
3. Admin reviews with `/titles` command
4. Admin approves/rejects:
   - **Approved**: Moved to `approved_titles.csv` + cache updated
   - **Rejected**: Moved to `rejected_titles.csv` with reason
5. Video title updated in database

### Bulk Approval Flow
1. Admin identifies trusted worker with high-quality submissions
2. Admin runs `/bulkapprove <worker_id>`
3. All pending titles from that worker are approved at once
4. Cache updated for all approved videos

## Data Storage

### Permissions Configuration
**File:** `permissions_config.json`
```json
{
  "admins": [123456789, 234567890],
  "workers": [345678901, 456789012],
  "settings": {
    "auto_save": true
  }
}
```

### Title Submissions CSVs
**Location:** `title_submissions/`

**pending_titles.csv:**
- submission_id
- timestamp
- worker_id
- worker_username
- video_url
- creator_name
- suggested_title
- status

**approved_titles.csv:**
- All fields from pending + approved_by, approved_at

**rejected_titles.csv:**
- All fields from pending + rejected_by, rejected_at, reason

### User Requests CSVs
**Location:** `requests/`

**creator_requests.csv:**
- request_id (format: CR-YYYYMMDDHHMMSS-userID)
- timestamp
- user_id
- platform
- username
- status

**content_requests.csv:**
- request_id (format: CT-YYYYMMDDHHMMSS-userID)
- timestamp
- user_id
- platform
- username
- content_details
- status

## Cache Integration

When a title is approved, the system automatically:
1. Updates the `video_links` table in the cache database
2. Updates the `content_items` table if the video exists there
3. Ensures all future queries return the new title

The cache update happens immediately upon approval, so users see the new titles right away.

## Monitoring & Maintenance

### Check Pending Items
```bash
# Check pending titles
cat title_submissions/pending_titles.csv | wc -l

# Check pending requests
cat requests/creator_requests.csv | grep pending | wc -l
cat requests/content_requests.csv | grep pending | wc -l
```

### Worker Performance
Use `/adminstats` in the bot to see:
- Number of pending submissions per worker
- Approval/rejection rates
- Total submissions

### Backup Data
```bash
# Backup all submission data
tar -czf submissions_backup_$(date +%Y%m%d).tar.gz \
  title_submissions/ requests/ permissions_config.json
```

## Troubleshooting

### Worker Can't Submit Titles
- Check they're added as worker: `python manage_permissions.py list`
- Ensure they're replying to a valid video message
- Check title length (3-200 characters)

### Approval Not Updating Cache
- Check if video URL exists in cache
- Look for error messages in bot logs
- Video may not be cached yet (approval still saves)

### Permission Changes Not Taking Effect
- Restart the bot after permission changes
- Check `permissions_config.json` is readable
- Verify correct user IDs (numeric only)

## Security Notes

1. **Admin Permissions**: Only give admin access to trusted users - they can approve any content
2. **Worker Permissions**: Workers can only submit titles, not approve them
3. **User IDs**: Store user IDs securely, they're sensitive information
4. **CSV Files**: Regularly backup the CSV files - they contain all submission history

## Future Enhancements

Potential improvements:
- Web dashboard for reviewing submissions
- Auto-approval based on worker reputation scores
- Title quality scoring (AI-based)
- Notification system for workers when titles are approved/rejected
- Analytics dashboard for submission trends

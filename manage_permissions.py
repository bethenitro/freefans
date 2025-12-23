"""
Permissions Setup Script - Manage admin and worker permissions from backend

Usage:
    python manage_permissions.py add-admin <user_id>
    python manage_permissions.py remove-admin <user_id>
    python manage_permissions.py add-worker <user_id>
    python manage_permissions.py remove-worker <user_id>
    python manage_permissions.py list
"""

import sys
from permissions_manager import get_permissions_manager


def show_usage():
    """Show usage information."""
    print(__doc__)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        show_usage()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    permissions = get_permissions_manager()
    
    if command == 'list':
        # List all admins and workers
        perms = permissions.get_all_permissions()
        
        print("\n📋 Current Permissions:\n")
        print(f"👑 Admins ({len(perms['admins'])}):")
        for admin_id in perms['admins']:
            print(f"  • {admin_id}")
        
        print(f"\n👷 Workers ({len(perms['workers'])}):")
        for worker_id in perms['workers']:
            print(f"  • {worker_id}")
        
        print()
    
    elif command == 'add-admin':
        if len(sys.argv) < 3:
            print("❌ Error: User ID required")
            print("Usage: python manage_permissions.py add-admin <user_id>")
            sys.exit(1)
        
        try:
            user_id = int(sys.argv[2])
        except ValueError:
            print("❌ Error: User ID must be a number")
            sys.exit(1)
        
        if permissions.add_admin(user_id):
            print(f"✅ User {user_id} added as admin")
        else:
            print(f"⚠️  User {user_id} is already an admin")
    
    elif command == 'remove-admin':
        if len(sys.argv) < 3:
            print("❌ Error: User ID required")
            print("Usage: python manage_permissions.py remove-admin <user_id>")
            sys.exit(1)
        
        try:
            user_id = int(sys.argv[2])
        except ValueError:
            print("❌ Error: User ID must be a number")
            sys.exit(1)
        
        if permissions.remove_admin(user_id):
            print(f"✅ User {user_id} removed from admins")
        else:
            print(f"⚠️  User {user_id} is not an admin")
    
    elif command == 'add-worker':
        if len(sys.argv) < 3:
            print("❌ Error: User ID required")
            print("Usage: python manage_permissions.py add-worker <user_id>")
            sys.exit(1)
        
        try:
            user_id = int(sys.argv[2])
        except ValueError:
            print("❌ Error: User ID must be a number")
            sys.exit(1)
        
        if permissions.add_worker(user_id):
            print(f"✅ User {user_id} added as worker")
        else:
            print(f"⚠️  User {user_id} is already a worker")
    
    elif command == 'remove-worker':
        if len(sys.argv) < 3:
            print("❌ Error: User ID required")
            print("Usage: python manage_permissions.py remove-worker <user_id>")
            sys.exit(1)
        
        try:
            user_id = int(sys.argv[2])
        except ValueError:
            print("❌ Error: User ID must be a number")
            sys.exit(1)
        
        if permissions.remove_worker(user_id):
            print(f"✅ User {user_id} removed from workers")
        else:
            print(f"⚠️  User {user_id} is not a worker")
    
    else:
        print(f"❌ Unknown command: {command}")
        show_usage()
        sys.exit(1)


if __name__ == '__main__':
    main()

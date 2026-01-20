#!/usr/bin/env python3

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Optional


# ============================================================================
# CONFIGURATION VARIABLES - EDIT THESE
# ============================================================================

# Git repository URL
GIT_REPO_URL = "https://github.com/bethenitro/freefans.git"

# Directory where the repository will be cloned
# Use /home/container for containerized environments, /opt/freefans for standard servers
CLONE_DIRECTORY = "/home/container/freefans"

# Python executable to use
PYTHON_EXECUTABLE = "python3"

# ============================================================================
# ENVIRONMENT VARIABLES - EDIT THESE
# ============================================================================

# RabbitMQ connection URL for Celery task broker
RABBITMQ_URL = "amqps://rqvfrody:Q1I5Z-vm0MkfvZVdkerUX7L7Q2vrY-iY@shrimp.rmq.cloudamqp.com/rqvfrody"

# Environment for the application (development, staging, production)
ENVIRONMENT = "production"

# Celery worker configuration
CELERY_CONCURRENCY = 4  # Number of concurrent tasks
CELERY_MAX_TASKS_PER_CHILD = 1000  # Restart worker after this many tasks

# Redis configuration (optional, used for caching)
REDIS_URL = ""  # Leave empty to disable or set to "redis://localhost:6379/0"

# Telegram bot token (will be read from user input if not set)
TELEGRAM_BOT_TOKEN = "8144252709:AAGlu0fwSu9sRrUN6fGZLVjhjVi_ts7GtZ8"

# Landing server configuration (optional)
LANDING_BASE_URL = ""
LANDING_SECRET_KEY = ""

# Additional environment variables
ADDITIONAL_ENV_VARS = {
    # Add any additional environment variables here as key-value pairs
    # Example: "LOG_LEVEL": "INFO",
    "SUPABASE_DATABASE_URL": "postgresql+psycopg2://postgres.lfbwiahuqnqxcmrfpxpa:DKYtCnGxUw8wBQ5d@aws-1-eu-central-2.pooler.supabase.com:6543/postgres",
    "LANDING_ENABLED":"true",
    "BOT_NAME": "FreeFansBot"
}

# ============================================================================
# LOGGING AND UTILITY FUNCTIONS
# ============================================================================

class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text:^70}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 70}{Colors.END}\n")


def print_section(text: str) -> None:
    """Print a formatted section header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}▶ {text}{Colors.END}")


def print_success(text: str) -> None:
    """Print success message."""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_info(text: str) -> None:
    """Print info message."""
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")


def print_warning(text: str) -> None:
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def run_command(command: list, description: str, cwd: Optional[str] = None) -> bool:
    """
    Execute a shell command.
    
    Args:
        command: Command as list of strings
        description: Human-readable description of what the command does
        cwd: Working directory for the command
        
    Returns:
        True if successful, False otherwise
    """
    try:
        print_info(description)
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            text=True,
            capture_output=False
        )
        print_success(f"{description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"{description} failed with exit code {e.returncode}")
        return False
    except FileNotFoundError as e:
        print_error(f"Command not found: {e}")
        return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def check_command_exists(command: str) -> bool:
    """Check if a command exists in PATH."""
    result = subprocess.run(
        ["which", command],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def get_user_input(prompt: str, default: Optional[str] = None) -> str:
    """
    Get user input with optional default value.
    
    Args:
        prompt: Prompt to display
        default: Default value if user provides empty input
        
    Returns:
        User input or default value
    """
    if default:
        prompt_text = f"{prompt} [{default}]: "
    else:
        prompt_text = f"{prompt}: "
    
    user_input = input(prompt_text).strip()
    return user_input if user_input else default


# ============================================================================
# SETUP FUNCTIONS
# ============================================================================

def check_prerequisites() -> bool:
    """Check if all prerequisites are installed."""
    print_section("Checking Prerequisites")
    
    prerequisites = [
        (PYTHON_EXECUTABLE, "Python 3"),
        ("git", "Git"),
    ]
    
    all_present = True
    for command, name in prerequisites:
        if check_command_exists(command):
            print_success(f"{name} is installed")
        else:
            print_error(f"{name} is NOT installed (required: {command})")
            all_present = False
    
    return all_present


def clone_repository() -> bool:
    """Clone the FreeFans repository."""
    print_section("Cloning Repository")
    
    repo_path = Path(CLONE_DIRECTORY)
    
    if repo_path.exists():
        print_warning(f"Directory already exists: {CLONE_DIRECTORY}")
        response = get_user_input(
            "Do you want to use the existing directory? (yes/no)",
            default="no"
        )
        if response.lower() != "yes":
            return False
        print_success("Using existing directory")
        return True
    
    # Create parent directory if needed
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    
    return run_command(
        ["git", "clone", GIT_REPO_URL, CLONE_DIRECTORY],
        f"Cloning repository from {GIT_REPO_URL}"
    )


def get_pip_path() -> str:
    """Get the pip command (using system Python)."""
    return "pip3"


def install_dependencies() -> bool:
    """Install Python dependencies using system Python with disk optimization."""
    print_section("Installing Dependencies")
    
    telegram_bot_dir = Path(CLONE_DIRECTORY) / "telegram_bot"
    pip_cmd = get_pip_path()
    
    # Upgrade pip with disk optimization
    if not run_command(
        [pip_cmd, "install", "--upgrade", "--no-cache-dir", "pip"],
        "Upgrading pip"
    ):
        return False
    
    # Install requirements
    requirements_file = telegram_bot_dir / "requirements.txt"
    if not requirements_file.exists():
        print_error(f"Requirements file not found: {requirements_file}")
        return False
    
    print_info("Installing dependencies (this may take several minutes)...")
    print_warning("Using aggressive disk optimization for containerized environments")
    print_info("Batch size: 2 packages | No cache | No build isolation | Continuous cleanup")
    print()
    
    try:
        # Read requirements file
        with open(requirements_file, 'r') as f:
            packages = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        total_packages = len(packages)
        batch_size = 2  # Install 2 packages at a time (further reduced for disk space)
        
        for i in range(0, total_packages, batch_size):
            batch = packages[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_packages + batch_size - 1) // batch_size
            
            print_info(f"Installing batch {batch_num}/{total_batches} ({len(batch)} packages)...")
            
            # Install with maximum disk optimization
            cmd = [
                pip_cmd,
                "install",
                "--no-cache-dir",           # Don't cache wheels
                "--no-build-isolation",     # Reduce temp files during build
                "--no-deps",                # Skip dependency resolution (handled later)
                "-q",                       # Quiet mode (less verbose)
            ]
            cmd.extend(batch)
            
            if not run_command(cmd, f"Batch {batch_num}/{total_batches}"):
                print_warning(f"Batch {batch_num} installation had issues, but continuing...")
            
            # Clean up after every 3 batches to avoid disk overflow
            if batch_num % 3 == 0:
                subprocess.run([pip_cmd, "cache", "purge"], capture_output=True)
                # Also clean tmp files
                subprocess.run(["find", "/tmp", "-type", "f", "-delete"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Final pass: install with dependency resolution in small chunks
        print_info("Running final dependency resolution pass...")
        
        # Clean pip cache before final pass
        print_info("Cleaning pip cache...")
        subprocess.run([pip_cmd, "cache", "purge"], capture_output=True)
        
        # Process final installation in small batches of 5 (reduced from 10)
        for i in range(0, len(packages), 5):
            batch = packages[i:i+5]
            batch_num = (i // 5) + 1
            
            cmd = [
                pip_cmd,
                "install",
                "--no-cache-dir",
                "--no-build-isolation",
                "-q",
            ]
            cmd.extend(batch)
            
            if not run_command(cmd, f"Final pass chunk {batch_num}"):
                print_warning(f"Final pass chunk {batch_num} had issues, continuing...")
            
            # Clean cache after each final pass chunk to avoid disk overflow
            subprocess.run([pip_cmd, "cache", "purge"], capture_output=True)
        
        # Clean cache again after installation
        print_info("Cleaning pip cache...")
        subprocess.run([pip_cmd, "cache", "purge"], capture_output=True)
        
        print_success("All packages installed successfully!")
        return True
    
    except Exception as e:
        print_error(f"Error during batch installation: {e}")
        return False


def create_env_file() -> bool:
    """Create .env file in telegram_bot directory."""
    print_section("Creating Environment Configuration")
    
    telegram_bot_dir = Path(CLONE_DIRECTORY) / "telegram_bot"
    env_file = telegram_bot_dir / ".env"
    
    # Prepare environment variables
    env_vars = {
        "RABBITMQ_URL": RABBITMQ_URL,
        "ENVIRONMENT": ENVIRONMENT,
        "CELERY_CONCURRENCY": str(CELERY_CONCURRENCY),
        "CELERY_MAX_TASKS_PER_CHILD": str(CELERY_MAX_TASKS_PER_CHILD),
    }
    
    # Add optional variables if set
    if TELEGRAM_BOT_TOKEN:
        env_vars["TELEGRAM_BOT_TOKEN"] = TELEGRAM_BOT_TOKEN
    else:
        token = get_user_input("Enter Telegram Bot Token (optional)")
        if token:
            env_vars["TELEGRAM_BOT_TOKEN"] = token
    
    if REDIS_URL:
        env_vars["REDIS_URL"] = REDIS_URL
    
    if LANDING_BASE_URL:
        env_vars["LANDING_BASE_URL"] = LANDING_BASE_URL
    
    if LANDING_SECRET_KEY:
        env_vars["LANDING_SECRET_KEY"] = LANDING_SECRET_KEY
    
    # Add additional environment variables
    env_vars.update(ADDITIONAL_ENV_VARS)
    
    try:
        # Check if .env already exists
        if env_file.exists():
            print_warning(f".env file already exists at {env_file}")
            response = get_user_input(
                "Do you want to overwrite it? (yes/no)",
                default="no"
            )
            if response.lower() != "yes":
                print_success("Keeping existing .env file")
                return True
        
        # Write .env file
        with open(env_file, "w") as f:
            f.write("# FreeFans Worker Bot Configuration\n")
            f.write("# Auto-generated by deploy_worker_bot.py\n\n")
            
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        
        print_success(f"Created .env file at {env_file}")
        return True
    except Exception as e:
        print_error(f"Failed to create .env file: {e}")
        return False


def verify_shared_directory() -> bool:
    """Verify that shared directory is available."""
    print_section("Verifying Shared Directory")
    
    repo_path = Path(CLONE_DIRECTORY)
    shared_dir = repo_path / "shared"
    
    if shared_dir.exists():
        print_success(f"Shared directory found at {shared_dir}")
        return True
    else:
        print_warning(f"Shared directory not found at {shared_dir}")
        print_info("The shared directory is required for the bot to function.")
        print_info("Please ensure it's available at the expected location.")
        
        response = get_user_input(
            "Continue anyway? (yes/no)",
            default="no"
        )
        return response.lower() == "yes"


def cleanup_disk() -> None:
    """Clean up temporary files and caches to save disk space."""
    print_section("Cleaning Up Temporary Files")
    
    try:
        # Clean pip cache
        print_info("Cleaning pip cache...")
        subprocess.run([get_pip_path(), "cache", "purge"], capture_output=True)
        print_success("Cleaned pip cache")
    except Exception as e:
        print_warning(f"Could not clean pip cache: {e}")
    
    try:
        # Clean apt cache (if using Debian-based container)
        print_info("Cleaning apt cache...")
        subprocess.run(["apt-get", "clean"], capture_output=True)
        subprocess.run(["rm", "-rf", "/var/lib/apt/lists/*"], capture_output=True)
        print_success("Cleaned apt cache")
    except Exception as e:
        print_warning(f"Could not clean apt cache: {e}")
    
    try:
        # Remove temporary Python files
        print_info("Cleaning /tmp directory...")
        subprocess.run(["find", "/tmp", "-type", "f", "-delete"], capture_output=True)
        print_success("Cleaned /tmp directory")
    except Exception as e:
        print_warning(f"Could not clean /tmp: {e}")
    
    try:
        # Remove .git directory to save space (keeps code but removes history)
        git_dir = Path(CLONE_DIRECTORY) / ".git"
        if git_dir.exists():
            print_info(f"Removing .git directory to save disk space...")
            subprocess.run(["rm", "-rf", str(git_dir)], capture_output=True)
            print_success(f"Removed .git directory (saved ~10-15MB)")
    except Exception as e:
        print_warning(f"Could not remove .git directory: {e}")
    
    try:
        # Remove __pycache__ directories
        print_info("Removing Python cache files...")
        subprocess.run(
            ["find", CLONE_DIRECTORY, "-type", "d", "-name", "__pycache__", "-exec", "rm", "-rf", "{}", "+"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print_success("Removed Python cache files")
    except Exception as e:
        print_warning(f"Could not remove __pycache__: {e}")
    
    try:
        # Remove .pyc files
        print_info("Removing .pyc files...")
        subprocess.run(
            ["find", CLONE_DIRECTORY, "-type", "f", "-name", "*.pyc", "-delete"],
            capture_output=True
        )
        print_success("Removed .pyc files")
    except Exception as e:
        print_warning(f"Could not remove .pyc files: {e}")
    
    try:
        # Remove unnecessary large directories from the repository
        print_info("Removing unnecessary directories...")
        unnecessary_dirs = [
            Path(CLONE_DIRECTORY) / "landing_server",  # Not needed for worker bot
            Path(CLONE_DIRECTORY) / "core",  # Duplicate in telegram_bot/core
            Path(CLONE_DIRECTORY) / "managers",  # Duplicate in telegram_bot/managers
            Path(CLONE_DIRECTORY) / "scrapers",  # Duplicate in telegram_bot/scrapers
            Path(CLONE_DIRECTORY) / "utilities",  # Not essential for worker
            Path(CLONE_DIRECTORY) / "scripts",  # Not needed for deployment
        ]
        for dir_path in unnecessary_dirs:
            if dir_path.exists():
                subprocess.run(["rm", "-rf", str(dir_path)], capture_output=True)
        print_success("Removed unnecessary directories (saved ~5-10MB)")
    except Exception as e:
        print_warning(f"Could not remove unnecessary directories: {e}")
    
    try:
        # Remove test files
        print_info("Removing test files...")
        subprocess.run(
            ["find", CLONE_DIRECTORY, "-type", "f", "-name", "*test*.py", "-delete"],
            capture_output=True
        )
        subprocess.run(
            ["find", CLONE_DIRECTORY, "-type", "d", "-name", "tests", "-exec", "rm", "-rf", "{}", "+"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print_success("Removed test files")
    except Exception as e:
        print_warning(f"Could not remove test files: {e}")
    
    try:
        # Remove documentation files
        print_info("Removing documentation files...")
        doc_patterns = ["*.md", "*.rst", "*.txt", "LICENSE*", "CHANGELOG*"]
        for pattern in doc_patterns:
            subprocess.run(
                ["find", CLONE_DIRECTORY, "-type", "f", "-name", pattern, "-delete"],
                capture_output=True
            )
        print_success("Removed documentation files")
    except Exception as e:
        print_warning(f"Could not remove documentation: {e}")
    
    try:
        # Remove unnecessary files from site-packages
        print_info("Removing unnecessary package files...")
        local_lib = Path.home() / ".local" / "lib"
        if local_lib.exists():
            # Remove .dist-info directories (metadata)
            subprocess.run(
                ["find", str(local_lib), "-type", "d", "-name", "*.dist-info", "-exec", "rm", "-rf", "{}", "+"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Remove .egg-info directories
            subprocess.run(
                ["find", str(local_lib), "-type", "d", "-name", "*.egg-info", "-exec", "rm", "-rf", "{}", "+"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Remove tests from installed packages
            subprocess.run(
                ["find", str(local_lib), "-type", "d", "-name", "tests", "-exec", "rm", "-rf", "{}", "+"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            subprocess.run(
                ["find", str(local_lib), "-type", "d", "-name", "test", "-exec", "rm", "-rf", "{}", "+"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print_success("Removed unnecessary package files (saved ~20-30MB)")
    except Exception as e:
        print_warning(f"Could not clean site-packages: {e}")


# ============================================================================
# STARTUP FUNCTION
# ============================================================================

def start_worker_bot() -> bool:
    """Start the worker bot using system Python."""
    print_section("Starting Worker Bot")
    
    telegram_bot_dir = Path(CLONE_DIRECTORY) / "telegram_bot"
    
    print_info(f"Python executable: {PYTHON_EXECUTABLE}")
    print_info(f"Working directory: {telegram_bot_dir}")
    print_info("Starting worker bot process...")
    print()
    
    try:
        subprocess.run(
            [PYTHON_EXECUTABLE, "worker_bot.py"],
            cwd=str(telegram_bot_dir),
            check=False
        )
        return True
    except Exception as e:
        print_error(f"Failed to start worker bot: {e}")
        return False


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main() -> int:
    """Main deployment function."""
    print_header("FreeFans Worker Bot Deployment")
    
    print_info("This script will deploy the FreeFans worker bot.")
    print_info("Configuration:")
    print(f"  Repository: {GIT_REPO_URL}")
    print(f"  Clone to: {CLONE_DIRECTORY}")
    print(f"  RabbitMQ: {RABBITMQ_URL}")
    print()
    
    # Step 1: Check prerequisites
    if not check_prerequisites():
        print_error("Prerequisites check failed!")
        print_error("Please install missing dependencies and try again.")
        return 1
    
    # Step 2: Clone repository
    if not clone_repository():
        print_error("Failed to clone repository")
        return 1
    
    # Step 3: Install dependencies
    if not install_dependencies():
        print_error("Failed to install dependencies")
        return 1
    
    # Step 4: Create .env file
    if not create_env_file():
        print_error("Failed to create .env file")
        return 1
    
    # Step 5: Verify shared directory
    if not verify_shared_directory():
        print_warning("Shared directory verification failed")
        print_info("Continuing anyway...")
    
    # Step 6: Clean up temporary files
    cleanup_disk()
    
    # Final summary
    print_header("Deployment Complete!")
    
    print_info("Summary:")
    print(f"  Repository location: {CLONE_DIRECTORY}")
    print(f"  Telegram bot directory: {CLONE_DIRECTORY}/telegram_bot")
    print(f"  Configuration file: {CLONE_DIRECTORY}/telegram_bot/.env")
    print()
    
    print_info("Next steps:")
    print("  1. Verify configuration in .env file")
    print(f"  2. Ensure RabbitMQ is running at {RABBITMQ_URL}")
    print("  3. Run the worker bot:")
    print(f"     {PYTHON_EXECUTABLE} {CLONE_DIRECTORY}/telegram_bot/worker_bot.py")
    print()
    
    # Ask if user wants to start the bot
    response = get_user_input(
        "Start the worker bot now? (yes/no)",
        default="yes"
    )
    
    if response.lower() == "yes":
        print_header("Starting Worker Bot")
        if start_worker_bot():
            return 0
        else:
            return 1
    
    print_success("Deployment script completed successfully!")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n")
        print_warning("Deployment interrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

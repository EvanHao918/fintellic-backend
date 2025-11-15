#!/usr/bin/env python3
"""
Database export script for Railway migration
Exports users, companies, and filings data to SQL file
"""
import subprocess
import sys
from datetime import datetime

def export_database():
    """Export database to SQL file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"fintellic_db_export_{timestamp}.sql"
    
    print(f"📦 Exporting database to {output_file}...")
    
    try:
        # Export entire database
        result = subprocess.run(
            ['pg_dump', 'fintellic_db', '-f', output_file],
            check=True,
            capture_output=True,
            text=True
        )
        
        print(f"✅ Database exported successfully!")
        print(f"📄 File: {output_file}")
        
        # Show file size
        import os
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        print(f"📊 Size: {size_mb:.2f} MB")
        
        return output_file
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Export failed: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ pg_dump not found. Is PostgreSQL installed?")
        sys.exit(1)

if __name__ == "__main__":
    export_database()

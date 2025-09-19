#!/usr/bin/env python3

import requests
import json
import time
import sys
from datetime import datetime
import tempfile
import os

class PhantomTalkAPITester:
    def __init__(self, base_url="https://phantomtalk-1.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED")
        else:
            print(f"❌ {name} - FAILED: {details}")
        
        self.test_results.append({
            'name': name,
            'success': success,
            'details': details
        })

    def test_api_health(self):
        """Test if API is accessible"""
        try:
            response = requests.get(f"{self.api_url}/messages", timeout=30)
            success = response.status_code in [200, 404, 422]  # Any valid HTTP response
            self.log_test("API Health Check", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("API Health Check", False, str(e))
            return False

    def test_get_messages(self):
        """Test getting messages endpoint"""
        try:
            response = requests.get(f"{self.api_url}/messages", timeout=30)
            success = response.status_code == 200
            if success:
                messages = response.json()
                self.log_test("GET Messages", True, f"Retrieved {len(messages)} messages")
            else:
                self.log_test("GET Messages", False, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("GET Messages", False, str(e))
            return False

    def test_create_text_message(self):
        """Test creating a text message"""
        try:
            data = {
                'content': 'Test message from backend test',
                'username': 'TestUser',
                'ttl_seconds': 3600,
                'send_to_discord': False
            }
            
            response = requests.post(f"{self.api_url}/messages", data=data, timeout=10)
            success = response.status_code in [200, 201]
            
            if success:
                message = response.json()
                self.log_test("Create Text Message", True, f"Message ID: {message.get('id', 'N/A')}")
                return message.get('id')
            else:
                self.log_test("Create Text Message", False, f"Status: {response.status_code}, Response: {response.text}")
                return None
        except Exception as e:
            self.log_test("Create Text Message", False, str(e))
            return None

    def test_create_message_with_file(self):
        """Test creating a message with file attachment"""
        try:
            # Create a temporary test file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write("This is a test file for PhantomTalk")
                temp_file_path = f.name
            
            data = {
                'content': 'Test message with file attachment',
                'username': 'TestUser',
                'ttl_seconds': 3600,
                'send_to_discord': False
            }
            
            with open(temp_file_path, 'rb') as f:
                files = {'file': ('test_file.txt', f, 'text/plain')}
                response = requests.post(f"{self.api_url}/messages", data=data, files=files, timeout=15)
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            success = response.status_code in [200, 201]
            
            if success:
                message = response.json()
                self.log_test("Create Message with File", True, f"File: {message.get('file_name', 'N/A')}")
                return message.get('id')
            else:
                self.log_test("Create Message with File", False, f"Status: {response.status_code}, Response: {response.text}")
                return None
        except Exception as e:
            self.log_test("Create Message with File", False, str(e))
            return None

    def test_blocked_file_upload(self):
        """Test that blocked file extensions are rejected"""
        try:
            # Create a temporary .php file (should be blocked)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False) as f:
                f.write("<?php echo 'test'; ?>")
                temp_file_path = f.name
            
            data = {
                'content': 'Test blocked file upload',
                'username': 'TestUser',
                'ttl_seconds': 3600,
                'send_to_discord': False
            }
            
            with open(temp_file_path, 'rb') as f:
                files = {'file': ('malicious.php', f, 'application/x-php')}
                response = requests.post(f"{self.api_url}/messages", data=data, files=files, timeout=10)
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            # Should return 400 for blocked file
            success = response.status_code == 400
            self.log_test("Blocked File Upload Security", success, f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("Blocked File Upload Security", False, str(e))
            return False

    def test_file_download(self, message_id):
        """Test file download functionality"""
        if not message_id:
            self.log_test("File Download", False, "No message ID provided")
            return False
            
        try:
            # First get the message to find file info
            response = requests.get(f"{self.api_url}/messages", timeout=10)
            if response.status_code != 200:
                self.log_test("File Download", False, "Could not retrieve messages")
                return False
            
            messages = response.json()
            target_message = None
            for msg in messages:
                if msg.get('id') == message_id and msg.get('file_path'):
                    target_message = msg
                    break
            
            if not target_message:
                self.log_test("File Download", False, "Message with file not found")
                return False
            
            # Extract file ID from file path
            file_path = target_message['file_path']
            file_id = file_path.split('/')[-1].split('.')[0]  # Get UUID part
            
            # Test file download
            download_response = requests.get(f"{self.api_url}/files/{file_id}", timeout=10)
            success = download_response.status_code == 200
            
            if success:
                self.log_test("File Download", True, f"Downloaded {len(download_response.content)} bytes")
            else:
                self.log_test("File Download", False, f"Status: {download_response.status_code}")
            
            return success
        except Exception as e:
            self.log_test("File Download", False, str(e))
            return False

    def test_ttl_functionality(self):
        """Test TTL (Time-To-Live) functionality with short TTL"""
        try:
            # Create message with 2 second TTL
            data = {
                'content': 'TTL test message - should expire in 2 seconds',
                'username': 'TTLTestUser',
                'ttl_seconds': 2,
                'send_to_discord': False
            }
            
            response = requests.post(f"{self.api_url}/messages", data=data, timeout=10)
            if response.status_code not in [200, 201]:
                self.log_test("TTL Functionality", False, f"Failed to create TTL message: {response.status_code}")
                return False
            
            message = response.json()
            message_id = message.get('id')
            
            # Immediately check if message exists
            messages_response = requests.get(f"{self.api_url}/messages", timeout=10)
            if messages_response.status_code != 200:
                self.log_test("TTL Functionality", False, "Could not retrieve messages")
                return False
            
            messages = messages_response.json()
            message_exists_before = any(msg.get('id') == message_id for msg in messages)
            
            if not message_exists_before:
                self.log_test("TTL Functionality", False, "Message not found immediately after creation")
                return False
            
            # Wait for TTL to expire (2 seconds + buffer)
            print("⏳ Waiting for TTL expiration (4 seconds)...")
            time.sleep(4)
            
            # Check if message is gone
            messages_response = requests.get(f"{self.api_url}/messages", timeout=10)
            if messages_response.status_code != 200:
                self.log_test("TTL Functionality", False, "Could not retrieve messages after TTL")
                return False
            
            messages = messages_response.json()
            message_exists_after = any(msg.get('id') == message_id for msg in messages)
            
            success = not message_exists_after
            self.log_test("TTL Functionality", success, f"Message expired as expected: {not message_exists_after}")
            return success
            
        except Exception as e:
            self.log_test("TTL Functionality", False, str(e))
            return False

    def test_discord_integration(self):
        """Test Discord webhook integration (without actually sending to avoid spam)"""
        try:
            # Test with send_to_discord=True but we can't verify actual Discord delivery
            # This tests that the API accepts the parameter without errors
            data = {
                'content': 'Discord integration test message',
                'username': 'DiscordTestUser',
                'ttl_seconds': 10,  # Short TTL to avoid clutter
                'send_to_discord': True
            }
            
            response = requests.post(f"{self.api_url}/messages", data=data, timeout=15)
            success = response.status_code in [200, 201]
            
            if success:
                self.log_test("Discord Integration API", True, "Discord flag accepted by API")
            else:
                self.log_test("Discord Integration API", False, f"Status: {response.status_code}")
            
            return success
        except Exception as e:
            self.log_test("Discord Integration API", False, str(e))
            return False

    def run_all_tests(self):
        """Run all backend API tests"""
        print("🚀 Starting PhantomTalk Backend API Tests")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Basic connectivity
        if not self.test_api_health():
            print("❌ API is not accessible. Stopping tests.")
            return False
        
        # Core functionality tests
        self.test_get_messages()
        
        # Message creation tests
        text_message_id = self.test_create_text_message()
        file_message_id = self.test_create_message_with_file()
        
        # Security tests
        self.test_blocked_file_upload()
        
        # File download test
        if file_message_id:
            self.test_file_download(file_message_id)
        
        # TTL functionality
        self.test_ttl_functionality()
        
        # Discord integration
        self.test_discord_integration()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        for result in self.test_results:
            status = "✅ PASS" if result['success'] else "❌ FAIL"
            print(f"{status} - {result['name']}")
            if not result['success'] and result['details']:
                print(f"    Details: {result['details']}")
        
        print(f"\n🎯 Overall: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All backend tests passed!")
            return True
        else:
            print("⚠️  Some backend tests failed. Check details above.")
            return False

def main():
    tester = PhantomTalkAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
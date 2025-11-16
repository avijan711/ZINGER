import win32com.client
import os
import subprocess
import requests
from typing import Optional
from PyQt6.QtWidgets import QMessageBox
from urllib.parse import quote

class ShareManager:
    """Manages sharing functionality including email and WhatsApp integration"""
    
    def __init__(self):
        self._outlook = None
    
    def _get_outlook(self) -> Optional[object]:
        """Get or create Outlook application instance"""
        if self._outlook is None:
            try:
                self._outlook = win32com.client.Dispatch('Outlook.Application')
            except Exception as e:
                print(f"Error connecting to Outlook: {e}")
                return None
        return self._outlook
    
    def share_via_email(self, file_path: str, subject: str = "", body: str = "") -> bool:
        """Share file via Outlook email"""
        try:
            outlook = self._get_outlook()
            if not outlook:
                print("Outlook not available")
                return False
            
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                return False
            
            try:
                # Create new email
                mail = outlook.CreateItem(0)  # 0 = olMailItem
                
                # Set email properties
                mail.Subject = subject or ""
                mail.Body = body or ""
                
                # Add attachment
                mail.Attachments.Add(os.path.abspath(file_path))
                
                # Display the email
                mail.Display(True)
            except Exception as e:
                error_msg = str(e).lower()
                if "dialog box is open" in error_msg or "תיבת הדו-שיח פתוחה" in error_msg:
                    QMessageBox.warning(
                        None,
                        "Warning",
                        "Please close any open Outlook windows and try again.\n"
                        "נא לסגור את כל החלונות הפתוחים של Outlook ולנסות שוב."
                    )
                else:
                    raise  # Re-raise other exceptions
            
            return True
            
        except Exception as e:
            print(f"Error creating email: {e}")
            return False
    
    def share_via_whatsapp(self, file_path: str) -> bool:
        """Share file via WhatsApp Desktop app"""
        try:
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                return False
            
            # Show upload progress
            QMessageBox.information(
                None,
                "Share via WhatsApp",
                "Please wait..."
            )
            
            # Upload file to 0x0.st
            with open(file_path, 'rb') as f:
                response = requests.post(
                    'https://0x0.st',
                    files={'file': f},
                    timeout=30  # 30 second timeout
                )
            
            if response.status_code != 200:
                raise Exception(f"Upload failed with status {response.status_code}")
            
            # Get download link
            download_link = response.text.strip()
            
            # Create WhatsApp message with just the link
            message = download_link
            
            # Open WhatsApp with the message
            whatsapp_url = f"whatsapp://send?text={quote(message)}"
            subprocess.run(['cmd', '/c', 'start', whatsapp_url], check=True)
            
            # Show success message
            QMessageBox.information(
                None,
                "Share via WhatsApp",
                "1. WhatsApp will open\n"
                "2. Select your contact\n"
                "3. The download link will be shared"
            )
            
            return True
            
        except requests.Timeout:
            print("[DEBUG] Upload timed out")
            QMessageBox.critical(
                None,
                "Error",
                "File upload timed out. Please try again or use a smaller file."
            )
            return False
        except subprocess.CalledProcessError as e:
            print(f"[DEBUG] Failed to open WhatsApp: {e}")
            QMessageBox.critical(
                None,
                "Error",
                "Failed to open WhatsApp. Please make sure WhatsApp Desktop is installed."
            )
            return False
        except Exception as e:
            print(f"[DEBUG] Error sharing via WhatsApp: {e}")
            QMessageBox.critical(
                None,
                "Error",
                f"Failed to share file: {str(e)}"
            )
            return False
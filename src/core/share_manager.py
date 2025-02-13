import win32com.client
import os
from typing import Optional

class ShareManager:
    """Manages sharing functionality including email integration"""
    
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
        """Create new email with file attached"""
        try:
            outlook = self._get_outlook()
            if not outlook:
                print("Outlook not available")
                return False
            
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                return False
            
            # Create new email
            mail = outlook.CreateItem(0)  # 0 = olMailItem
            
            # Set email properties
            mail.Subject = subject or "Signed Document"
            mail.Body = body or "Please find attached the signed document."
            
            # Add attachment
            mail.Attachments.Add(os.path.abspath(file_path))
            
            # Display the email
            mail.Display(True)
            
            return True
            
        except Exception as e:
            print(f"Error creating email: {e}")
            return False
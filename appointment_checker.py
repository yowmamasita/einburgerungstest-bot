import httpx
from bs4 import BeautifulSoup
from typing import Optional, Dict, List
import logging
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class AppointmentChecker:
    def __init__(self):
        self.base_url = "https://service.berlin.de"
        # Don't follow redirects automatically - we need to handle cookies manually
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"macOS"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
            follow_redirects=False,  # Handle redirects manually to manage cookies
            timeout=30.0,
            verify=True
        )
        
        # VHS locations with their IDs and names
        self.vhs_locations = {
            '122671': 'Volkshochschule Treptow-Köpenick',
            '325853': 'Volkshochschule City West',
            '351438': 'Volkshochschule Friedrichshain-Kreuzberg (Standort Friedrichshain)',
            '351444': 'Volkshochschule Friedrichshain-Kreuzberg (Standort Kreuzberg)',
            '122626': 'Volkshochschule Lichtenberg',
            '122628': 'Volkshochschule Marzahn-Hellersdorf',
            '351636': 'Volkshochschule Mitte - Antonstraße',
            '122659': 'Volkshochschule Neukölln',
            '122664': 'Volkshochschule Reinickendorf',
            '122666': 'Volkshochschule Spandau',
            '325987': 'Volkshochschule Steglitz-Zehlendorf - Goethestraße',
            '351435': 'Volkshochschule Tempelhof-Schöneberg'
        }
        
    def check_appointments(self) -> Dict:
        all_appointments = []
        errors = []
        location_check_times = {}
        
        # Check all VHS locations
        for location_id, location_name in self.vhs_locations.items():
            try:
                logger.info(f"Checking {location_name}...")
                
                if location_id == '122671':
                    # Special URL for Treptow-Köpenick
                    url = (
                        f"{self.base_url}/terminvereinbarung/termin/tag.php"
                        f"?id=4067&anliegen%5b%5d=351180&termin=1&dienstleister=122671&anliegen[]=351180"
                    )
                else:
                    # Standard URL format for other locations
                    url = (
                        f"{self.base_url}/terminvereinbarung/termin/tag.php"
                        f"?termin=1&dienstleisterlist={location_id}&anliegenlist=351180"
                    )
                
                # Follow redirect chain with cookie handling
                final_response = self._follow_redirects_with_cookies(url)
                
                # Record check time for this location
                location_check_times[location_name] = datetime.now().isoformat()
                
                if final_response and final_response.status_code == 200:
                    location_appointments = self._parse_appointments(
                        final_response.text, 
                        location_name, 
                        location_id,
                        str(final_response.url)
                    )
                    if location_appointments.get('appointments'):
                        all_appointments.extend(location_appointments['appointments'])
                elif final_response:
                    logger.warning(f"Failed to check {location_name}: HTTP {final_response.status_code}")
                    errors.append(f"{location_name}: HTTP {final_response.status_code}")
                else:
                    logger.warning(f"Failed to check {location_name}: No response")
                    errors.append(f"{location_name}: No response")
                    
            except Exception as e:
                logger.error(f"Error checking {location_name}: {e}")
                errors.append(f"{location_name}: {str(e)}")
        
        return {
            "status": "success" if not errors else "partial_success",
            "appointments": all_appointments,
            "total_available": len(all_appointments),
            "checked_at": datetime.now().isoformat(),
            "location_check_times": location_check_times,
            "errors": errors if errors else None
        }
    
    def _follow_redirects_with_cookies(self, initial_url: str, max_redirects: int = 5) -> Optional[httpx.Response]:
        """Follow redirect chain while maintaining cookies"""
        cookies = {}
        current_url = initial_url
        redirect_count = 0
        response = None
        
        while redirect_count < max_redirects:
            try:
                # Make request with accumulated cookies
                response = self.client.get(current_url, cookies=cookies)
                
                # Extract and save cookies from response
                if 'set-cookie' in response.headers:
                    cookie_header = response.headers.get('set-cookie')
                    if 'Zmsappointment=' in cookie_header:
                        cookie_value = cookie_header.split('Zmsappointment=')[1].split(';')[0]
                        cookies['Zmsappointment'] = cookie_value
                        logger.debug(f"Cookie set: Zmsappointment={cookie_value[:10]}...")
                
                # Check for redirect
                if response.status_code in [301, 302, 303, 307, 308]:
                    location = response.headers.get('location', '')
                    if location:
                        # Build absolute URL if relative
                        if not location.startswith('http'):
                            current_url = self.base_url + location
                        else:
                            current_url = location
                        
                        logger.debug(f"Redirecting to: {location}")
                        redirect_count += 1
                    else:
                        # No location header, stop
                        break
                else:
                    # Not a redirect, we've reached the final destination
                    break
                    
            except Exception as e:
                logger.error(f"Error following redirect: {e}")
                return None
        
        if redirect_count >= max_redirects:
            logger.warning(f"Max redirects ({max_redirects}) reached")
        
        return response
    
    def _parse_appointments(self, html: str, location_name: str, location_id: str, final_url: str = "") -> Dict:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            appointments = []
            
            # Check if we're on a "no appointments" page based on URL
            if '/terminvereinbarung/termin/stop/' in final_url:
                logger.debug(f"No appointments at {location_name} (stop page)")
                return {"status": "no_appointments", "appointments": [], "location": location_name}
            elif '/terminvereinbarung/termin/taken/' in final_url:
                logger.debug(f"No appointments at {location_name} (taken page)")
                return {"status": "no_appointments", "appointments": [], "location": location_name}
            
            # Look for available appointments (buchbar = bookable)
            # Check for calendar container
            calendar_container = soup.find('div', class_='calendar-month-table')
            if calendar_container:
                available_days = soup.find_all('td', class_='buchbar')
            else:
                # Alternative: look for any links with 'buchbar' class or appointment-related classes
                available_days = soup.find_all(['td', 'a'], class_=['buchbar', 'calendar-week-day'])
            
            # If we found any available days, mark this location as having appointments
            if available_days:
                appointments.append({
                    'location_name': location_name,
                    'location_id': location_id,
                    'has_slots': True,
                    'slot_count': len(available_days)
                })
            
            # Check if page indicates no appointments
            no_appointments_indicators = [
                soup.find('div', class_='alert-warning'),
                soup.find('div', class_='alert'),
                soup.find(text=lambda t: t and 'keine' in t.lower() and 'termin' in t.lower())
            ]
            
            has_no_appointments = any(indicator for indicator in no_appointments_indicators)
            
            if has_no_appointments and not appointments:
                logger.debug(f"No appointments available at {location_name}")
                return {
                    "status": "no_appointments",
                    "appointments": [],
                    "location": location_name
                }
            
            if appointments:
                logger.info(f"Found {len(appointments)} appointment(s) at {location_name}")
            
            return {
                "status": "success",
                "appointments": appointments,
                "location": location_name
            }
            
        except Exception as e:
            logger.error(f"Error parsing appointments for {location_name}: {e}")
            return {
                "status": "parse_error",
                "error": str(e),
                "appointments": [],
                "location": location_name
            }
    
    def close(self):
        self.client.close()
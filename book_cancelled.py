import urllib.parse
import os
import requests
import json
import time
from datetime import datetime, timedelta

# --- CONFIGURATION ---
TARGET_DATE = "2026-01-27"  # Date spécifique cible
TARGET_TIME = "13:30"       # Heure du créneau
DURATION = 3600             # 60 minutes
MAX_BOOKINGS = 1            
TIMEOUT_MINUTES = 5         # On insiste pendant 5 min après minuit
EMAIL = os.getenv("PADEL_EMAIL")
PASSWORD = os.getenv("PADEL_PASSWORD")
# ---------------------

class MouratoglouSniper:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.base_url = "https://api-blockout.doinsport.club"
        self.club_id = "652b9a65-0756-4f08-9b30-e20130aeea42"
        self.activity_id = "700a126b-59e1-4f94-8931-0c87483c6f10"
        self.user_client_id = "e0af1023-a752-4f0a-9d90-c03556d27382"
        self.partner_ids = [
            "2dcb5caf-37d5-4fc2-be7d-764ef371e40c",
            "5bc14b1b-9969-4fdf-853a-37a6c224ab59",
            "61634271-297b-4fd0-92d5-4a038ba41374"
        ]
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://mouratogloucc.doinsport.club',
            'Referer': 'https://mouratogloucc.doinsport.club/',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'X-Locale': 'fr'
        })

    def login(self):
        url = f"{self.base_url}/client_login_check"
        payload = {"username": self.email, "password": self.password, "club": f"/clubs/{self.club_id}", "origin": "white_label_app"}
        try:
            r = self.session.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                token = r.json().get('token')
                self.session.headers.update({'Authorization': f"Bearer {token}"})
                print(f"✅ Connexion réussie [{datetime.now().strftime('%H:%M:%S')}]")
                return True
            return False
        except:
            return False

    def find_slot(self):
        # On cible uniquement TARGET_DATE
        url = f"{self.base_url}/clubs/playgrounds/plannings/{TARGET_DATE}"
        params = {'club.id': self.club_id, 'activities.id': self.activity_id, 'bookingType': 'unique'}
        try:
            r = self.session.get(url, params=params, timeout=3)
            if r.status_code == 200:
                data = r.json()
                courts = data if isinstance(data, list) else data.get('hydra:member', [])
                for court in courts:
                    for act in court.get('activities', []):
                        for slot in act.get('slots', []):
                            if slot.get('startAt') == TARGET_TIME:
                                for p in slot.get('prices', []):
                                    if p.get('duration') == DURATION and p.get('bookable'):
                                        return {
                                            "price_id": p.get('id'),
                                            "p_id": court.get('id'),
                                            "court_name": court.get('name'),
                                            "price": p.get('pricePerParticipant', 1500)
                                        }
            return None
        except:
            return None

    def book(self, details):
        start_dt = datetime.strptime(f"{TARGET_DATE} {TARGET_TIME}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(seconds=DURATION)

        parts = [{"user": f"/user-clients/{self.user_client_id}", "restToPay": details['price'], "bookingOwner": True}]
        for pid in self.partner_ids:
            parts.append({"client": f"/clubs/clients/{pid}", "restToPay": details['price'], "bookingOwner": False})

        post_payload = {
            "timetableBlockPrice": f"/clubs/playgrounds/timetables/blocks/prices/{details['price_id']}",
            "activity": f"/activities/{self.activity_id}",
            "club": f"/clubs/{self.club_id}",
            "name": "kubler / PADEL",
            "startAt": f"{TARGET_DATE} {TARGET_TIME}:00",
            "endAt": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "playgrounds": [f"/clubs/playgrounds/{details['p_id']}"],
            "userClient": f"/user-clients/{self.user_client_id}",
            "participants": parts,
            "paymentMethod": "on_the_spot",
            "creationOrigin": "white_label_app"
        }

        print(f"\n🚀 TENTATIVE RÉSERVATION sur {details['court_name']}...")
        resp = self.session.post(f"{self.base_url}/clubs/bookings", json=post_payload)

        if resp.status_code not in [200, 201]:
            print(f"❌ Erreur POST: {resp.text}")
            return False

        booking_data = resp.json()
        booking_id = booking_data.get('id')

        # Confirmation PUT
        confirm_payload = {}
        for key, value in booking_data.items():
            if isinstance(value, dict) and '@id' in value: confirm_payload[key] = value['@id']
            elif isinstance(value, list): confirm_payload[key] = [item['@id'] if isinstance(item, dict) and '@id' in item else item for item in value]
            else: confirm_payload[key] = value

        confirm_payload["confirmed"] = True
        put_resp = self.session.put(f"{self.base_url}/clubs/bookings/{booking_id}", json=confirm_payload)

        if put_resp.status_code in [200, 201, 204]:
            print(f"🎊 RÉUSSI : {TARGET_DATE} à {TARGET_TIME}")
            return True
        return False

def wait_for_midnight(bot):
    now = datetime.now()
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    while True:
        now = datetime.now()
        remaining = (midnight - now).total_seconds()
        
        if remaining <= 0.5:
            print("\n🚀 C'EST L'HEURE ! Lancement...")
            break
        
        # Refresh token 30 secondes avant minuit pour être sûr
        if 30.0 < remaining < 31.0:
            print("🔄 Refreshing token avant le drop...")
            bot.login()
            time.sleep(1.1)

        print(f"⏳ Attente : {int(remaining)}s avant minuit...", end='\r')
        time.sleep(0.5)

def send_whatsapp_notification(message):
    phone = os.getenv("TEXTMEBOT_PHONE")
    apikey = os.getenv("TEXTMEBOT_API_KEY")
    if not (phone and apikey): return
    url = f"https://api.textmebot.com/send.php?recipient={phone}&apikey={apikey}&text={urllib.parse.quote(message)}"
    try: requests.get(url, timeout=5)
    except: pass

def run():
    bot = MouratoglouSniper(EMAIL, PASSWORD)
    if not bot.login():
        print("❌ Login initial échoué.")
        return

    # Phase d'attente
    #wait_for_midnight(bot)

    start_shoot = time.time()
    success = False

    # Boucle agressive pendant TIMEOUT_MINUTES
    while (time.time() - start_shoot) < (TIMEOUT_MINUTES * 60):
        print(f"🔎 Scan {TARGET_DATE} @ {TARGET_TIME}...", end='\r')
        slot = bot.find_slot()
        if slot:
            if bot.book(slot):
                success = True
                break
        
        # Très peu de repos au début pour être le premier
        time.sleep(0.2)

    msg = f"🏁 Sniper terminé. Résultat : {'SUCCÈS' if success else 'ÉCHEC'}"
    print(f"\n{msg}")
    send_whatsapp_notification(msg)

if __name__ == "__main__":
    run()

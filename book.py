import os
import requests
import json
import time
from datetime import datetime, timedelta

# --- CONFIGURATION ---
TARGET_TIME = "12:30"       # HEURE STRICTE
DURATION = 3600             # 60 minutes
MAX_BOOKINGS = 1            # Max 2 réservations par session
TIMEOUT_MINUTES = 3         # S'arrête après 5 minutes
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
        self.headers = {
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://mouratogloucc.doinsport.club',
            'Referer': 'https://mouratogloucc.doinsport.club/',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'X-Locale': 'fr'
        }

    def login(self):
        url = f"{self.base_url}/client_login_check"
        payload = {"username": self.email, "password": self.password, "club": f"/clubs/{self.club_id}", "origin": "white_label_app"}
        r = requests.post(url, json=payload, headers=self.headers)
        if r.status_code == 200:
            self.headers['Authorization'] = f"Bearer {r.json().get('token')}"
            print("✅ Connexion réussie.")
            return True
        return False

    def get_valid_target_dates(self):
        valid_dates = []
        today = datetime.now()
        for i in range(8, 1, -1): # Priorité J+8 vers J+2
            future_date = today + timedelta(days=i)
            if future_date.weekday() < 5: # Uniquement jours de semaine
                valid_dates.append(future_date.strftime("%Y-%m-%d"))
        return valid_dates

    def find_slot(self, target_date):
        url = f"{self.base_url}/clubs/playgrounds/plannings/{target_date}"
        params = {'club.id': self.club_id, 'activities.id': self.activity_id, 'bookingType': 'unique'}
        r = requests.get(url, headers=self.headers, params=params)

        if r.status_code == 200:
            data = r.json()
            courts = data if isinstance(data, list) else data.get('hydra:member', [])
            for court in courts:
                for act in court.get('activities', []):
                    for slot in act.get('slots', []):
                        # --- VÉRIFICATION STRICTE DE L'HORAIRE ---
                        if slot.get('startAt') == TARGET_TIME:
                            for p in slot.get('prices', []):
                                if p.get('duration') == DURATION and p.get('bookable'):
                                    return {
                                        "price_id": p.get('id'),
                                        "p_id": court.get('id'),
                                        "court_name": court.get('name'),
                                        "price": p.get('pricePerParticipant', 1500),
                                        "date": target_date,
                                        "start_time": slot.get('startAt') # Stocké pour double-check
                                    }
        return None

    def book(self, details):
        # --- DOUBLE-CHECK AVANT RÉSERVATION ---
        if details['start_time'] != TARGET_TIME:
            print(f"⚠️ ERREUR CRITIQUE : L'horaire détecté ({details['start_time']}) ne correspond pas à la cible ({TARGET_TIME}).")
            return False

        date_str = details['date']
        start_dt = datetime.strptime(f"{date_str} {TARGET_TIME}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(seconds=DURATION)

        parts = [{"user": f"/user-clients/{self.user_client_id}", "restToPay": details['price'], "bookingOwner": True}]
        for pid in self.partner_ids:
            parts.append({"client": f"/clubs/clients/{pid}", "restToPay": details['price'], "bookingOwner": False})

        # --- ETAPE 1 : POST ---
        post_payload = {
            "timetableBlockPrice": f"/clubs/playgrounds/timetables/blocks/prices/{details['price_id']}",
            "activity": f"/activities/{self.activity_id}",
            "club": f"/clubs/{self.club_id}",
            "name": "kubler / PADEL / PADEL / PADEL",
            "startAt": f"{date_str} {TARGET_TIME}:00",
            "endAt": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "playgrounds": [f"/clubs/playgrounds/{details['p_id']}"],
            "userClient": f"/user-clients/{self.user_client_id}",
            "participants": parts,
            "paymentMethod": "on_the_spot",
            "creationOrigin": "white_label_app"
        }

        print(f"\n🚀 [BOOKING] {details['court_name']} le {date_str} à {TARGET_TIME}")
        resp = requests.post(f"{self.base_url}/clubs/bookings", json=post_payload, headers=self.headers)

        if resp.status_code not in [200, 201]:
            print(f"❌ Échec POST: {resp.text}")
            return False

        booking_data = resp.json()
        booking_id = booking_data.get('id')

        # --- ETAPE 2 : PUT (CONFIRMATION) ---
        confirm_payload = {}
        for key, value in booking_data.items():
            if isinstance(value, dict) and '@id' in value:
                confirm_payload[key] = value['@id']
            elif isinstance(value, list):
                confirm_payload[key] = [item['@id'] if isinstance(item, dict) and '@id' in item else item for item in value]
            else:
                confirm_payload[key] = value

        confirm_payload["confirmed"] = True
        put_url = f"{self.base_url}/clubs/bookings/{booking_id}"
        put_resp = requests.put(put_url, json=confirm_payload, headers=self.headers)

        if put_resp.status_code in [200, 201, 204]:
            print(f"🎊 SUCCÈS CONFIRMÉ : {date_str} à {TARGET_TIME}")
            return True
        return False


def send_whatsapp_notification(message):
    phone = os.getenv("TEXTMEBOT_PHONE")
    apikey = os.getenv("TEXTMEBOT_API_KEY")
    
    if not phone or not apikey:
        print("⚠️ WhatsApp (TextMeBot) non configuré.")
        return

    # Encodage du message
    encoded_message = urllib.parse.quote(message)
    
    # URL spécifique à TextMeBot
    url = f"https://api.textmebot.com/whatsapp.php?recipient={phone}&apikey={apikey}&text={encoded_message}"
    
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            print("📱 Notification WhatsApp envoyée via TextMeBot !")
        else:
            print(f"❌ Erreur TextMeBot : {r.status_code} - {r.text}")
    except Exception as e:
        print(f"⚠️ Impossible d'envoyer le message : {e}")

def run():
    bot = MouratoglouSniper(EMAIL, PASSWORD)
    if bot.login():
        success_count = 0
        booked_dates = []
        start_time = time.time()
        timeout = TIMEOUT_MINUTES * 60

        print(f"🔥 Sniper calibré sur {TARGET_TIME} (Vérification stricte active)")

        while success_count < MAX_BOOKINGS:
            # Vérification du timeout
            if (time.time() - start_time) > timeout:
                print("\n⏱️ Temps limite atteint (5 min). Arrêt.")
                break

            dates = bot.get_valid_target_dates()
            for date in dates:
                if date in booked_dates: continue

                print(f"🔎 Scan : {date} @ {TARGET_TIME}...", end='\r')

                slot = bot.find_slot(date)
                if slot:
                    # Le check final est à l'intérieur de book()
                    if bot.book(slot):
                        success_count += 1
                        booked_dates.append(date)
                        print(f"✅ Status : {success_count}/{MAX_BOOKINGS} réservé(s)")
                        if success_count >= MAX_BOOKINGS: break
                time.sleep(0.4)

            if success_count < MAX_BOOKINGS:
                time.sleep(15)

        print(f"\n🏁 Session terminée. Total réservations : {success_count}")
        send_whatsapp_notification("\n🏁 Session terminée. Total réservations : {success_count}")

if __name__ == "__main__":
    run()

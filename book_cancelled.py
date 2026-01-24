import os
import requests
import json
import time
from datetime import datetime, timedelta

# --- CONFIGURATION ---
TARGET_TIME = "12:30"        # Heure du créneau cible
DURATION = 3600              # 60 minutes (3600 secondes)
MAX_BOOKINGS = 1             # S'arrête après 1 réservation réussie
TIMEOUT_SECONDS = 10         # Temps d'insistance par date (en minutes)
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
        payload = {
            "username": self.email, 
            "password": self.password, 
            "club": f"/clubs/{self.club_id}", 
            "origin": "white_label_app"
        }
        try:
            r = self.session.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                token = r.json().get('token')
                self.session.headers.update({'Authorization': f"Bearer {token}"})
                print(f"✅ Connexion réussie [{datetime.now().strftime('%H:%M:%S')}]")
                return True
            print(f"❌ Échec connexion: {r.status_code}")
            return False
        except Exception as e:
            print(f"⚠️ Erreur Login: {e}")
            return False

    def find_slot(self, target_date):
        url = f"{self.base_url}/clubs/playgrounds/plannings/{target_date}"
        params = {
            'club.id': self.club_id, 
            'activities.id': self.activity_id, 
            'bookingType': 'unique'
        }
        try:
            r = self.session.get(url, params=params, timeout=3)
            if r.status_code == 200:
                data = r.json()
                courts = data if isinstance(data, list) else data.get('hydra:member', [])
                for court in courts:
                    for act in court.get('activities', []):
                        for slot in act.get('slots', []):
                            # VERIFICATION STRICTE DE L'HEURE
                            if slot.get('startAt') == TARGET_TIME:
                                # --- BLOC DEBUG ---
                                print(f"\n🔍 SLOT TROUVÉ sur {court.get('name')} à {TARGET_TIME}")
    
                                # ------------------
                                
                                for p in slot.get('prices', []):
                                    if p.get('duration') == DURATION and p.get('bookable'):
                                        return {
                                            "price_id": p.get('id'),
                                            "p_id": court.get('id'),
                                            "court_name": court.get('name'),
                                            "price": p.get('pricePerParticipant', 1500),
                                            "real_start": slot.get('startAt')
                                        }
            return None
        except Exception as e:
            print(f"⚠️ Erreur Scan: {e}")
            return None

    def book(self, details, target_date):
        # On utilise l'heure confirmée par le scan
        start_time = details['real_start']
        start_dt = datetime.strptime(f"{target_date} {start_time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(seconds=DURATION)

        parts = [{"user": f"/user-clients/{self.user_client_id}", "restToPay": details['price'], "bookingOwner": True}]
        for pid in self.partner_ids:
            parts.append({"client": f"/clubs/clients/{pid}", "restToPay": details['price'], "bookingOwner": False})

        # Payload avec format ISO "T" pour éviter les ambiguïtés
        post_payload = {
            "timetableBlockPrice": f"/clubs/playgrounds/timetables/blocks/prices/{details['price_id']}",
            "activity": f"/activities/{self.activity_id}",
            "club": f"/clubs/{self.club_id}",
            "name": "kubler / PADEL",
            "startAt": f"{target_date}T{start_time}:00",
            "endAt": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "playgrounds": [f"/clubs/playgrounds/{details['p_id']}"],
            "userClient": f"/user-clients/{self.user_client_id}",
            "participants": parts,
            "paymentMethod": "on_the_spot",
            "creationOrigin": "white_label_app"
        }

        print(f"🚀 TENTATIVE RÉSERVATION sur {details['court_name']} pour {start_time}...")
        resp = self.session.post(f"{self.base_url}/clubs/bookings", json=post_payload)

        if resp.status_code not in [200, 201]:
            print(f"❌ Erreur POST: {resp.text}")
            return False

        booking_data = resp.json()
        booking_id = booking_data.get('id')

        # Préparation de la confirmation (PUT)
        confirm_payload = {}
        for key, value in booking_data.items():
            if isinstance(value, dict) and '@id' in value: 
                confirm_payload[key] = value['@id']
            elif isinstance(value, list): 
                confirm_payload[key] = [item['@id'] if isinstance(item, dict) and '@id' in item else item for item in value]
            else: 
                confirm_payload[key] = value

        confirm_payload["confirmed"] = True
        put_resp = self.session.put(f"{self.base_url}/clubs/bookings/{booking_id}", json=confirm_payload)

        if put_resp.status_code in [200, 201, 204]:
            print(f"🎊 RÉUSSI : {target_date} à {start_time}")
            return True
        return False

def get_target_dates():
    """Génère la liste des dates de J+1 à J+8 en excluant les weekends."""
    valid_dates = []
    today = datetime.now()
    for i in range(1, 9):
        future_date = today + timedelta(days=i)
        # 0=Lundi, 4=Vendredi
        if future_date.weekday() < 5: 
            valid_dates.append(future_date.strftime('%Y-%m-%d'))
    return valid_dates

def run():
    bot = MouratoglouSniper(EMAIL, PASSWORD)
    if not bot.login():
        return

    dates_to_check = get_target_dates()
    print(f"📅 Dates ciblées : {', '.join(dates_to_check)}")
    
    success_count = 0

    for current_target in dates_to_check:
        print(f"\n--- ⏳ Vérification : {current_target} ---")
        start_shoot = time.time()
        
        while (time.time() - start_shoot) < (TIMEOUT_SECONDS):
            print(f"🔎 Scan {current_target} @ {TARGET_TIME}...", end='\r')
            slot = bot.find_slot(current_target)
            
            if slot:
                if bot.book(slot, current_target):
                    success_count += 1
                    break # Succès pour cette date, on passe à la suivante
            
            time.sleep(1) # Un peu de repos pour l'API
        
        if success_count >= MAX_BOOKINGS:
            print(f"\n🎯 Quota de {MAX_BOOKINGS} réservation(s) atteint.")
            break

    print(f"\n🏁 Fin du script. Réservations effectuées : {success_count}")

if __name__ == "__main__":
    run()

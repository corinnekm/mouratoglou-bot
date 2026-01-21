import os
import requests
import json
import time
from datetime import datetime, timedelta

# --- CONFIGURATION ---
TARGET_TIME = "14:30"        # Heure du créneau
DURATION = 3600              # 60 minutes
MAX_BOOKINGS = 1             # S'arrête après un succès
TIMEOUT_MINUTES = 10         # Temps d'acharnement par date
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

    def find_all_slots(self, target_date):
        url = f"{self.base_url}/clubs/playgrounds/plannings/{target_date}"
        params = {'club.id': self.club_id, 'activities.id': self.activity_id, 'bookingType': 'unique'}
        available_slots = [] # On va lister TOUS les terrains libres
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
                                        available_slots.append({
                                            "price_id": p.get('id'),
                                            "p_id": court.get('id'),
                                            "court_name": court.get('name'),
                                            "price": p.get('pricePerParticipant', 1500)
                                        })
            return available_slots
        except:
            return []

    def find_slot(self, target_date):
        url = f"{self.base_url}/clubs/playgrounds/plannings/{target_date}"
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

    def book(self, details, target_date):
        start_dt = datetime.strptime(f"{target_date} {TARGET_TIME}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(seconds=DURATION)

        parts = [{"user": f"/user-clients/{self.user_client_id}", "restToPay": details['price'], "bookingOwner": True}]
        for pid in self.partner_ids:
            parts.append({"client": f"/clubs/clients/{pid}", "restToPay": details['price'], "bookingOwner": False})

        # Remplace cette partie dans ta fonction book() :
        post_payload = {
            "timetableBlockPrice": f"/clubs/playgrounds/timetables/blocks/prices/{details['price_id']}",
            "activity": f"/activities/{self.activity_id}",
            "club": f"/clubs/{self.club_id}",
            "name": "kubler / PADEL",
            # On remplace l'espace par un 'T'
            "startAt": f"{target_date}T{TARGET_TIME}:00", 
            "endAt": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "playgrounds": [f"/clubs/playgrounds/{details['p_id']}"],
            "userClient": f"/user-clients/{self.user_client_id}",
            "participants": parts,
            "paymentMethod": "on_the_spot",
            "creationOrigin": "white_label_app"
        }

        print(f"\n🚀 TENTATIVE RÉSERVATION [{target_date}] sur {details['court_name']}...")
        resp = self.session.post(f"{self.base_url}/clubs/bookings", json=post_payload)

        if resp.status_code not in [200, 201]:
            print(f"❌ Erreur POST: {resp.text}")
            return False

        booking_data = resp.json()
        booking_id = booking_data.get('id')

        confirm_payload = {}
        for key, value in booking_data.items():
            if isinstance(value, dict) and '@id' in value: confirm_payload[key] = value['@id']
            elif isinstance(value, list): confirm_payload[key] = [item['@id'] if isinstance(item, dict) and '@id' in item else item for item in value]
            else: confirm_payload[key] = value

        confirm_payload["confirmed"] = True
        put_resp = self.session.put(f"{self.base_url}/clubs/bookings/{booking_id}", json=confirm_payload)

        if put_resp.status_code in [200, 201, 204]:
            print(f"🎊 RÉUSSI : {target_date} à {TARGET_TIME}")
            return True
        return False

def get_target_dates():
    """Génère la liste des dates de J+1 à J+8 en excluant les weekends."""
    valid_dates = []
    today = datetime.now()
    for i in range(1, 9):
        future_date = today + timedelta(days=i)
        # weekday() : 0=Lundi, 4=Vendredi, 5=Samedi, 6=Dimanche
        if future_date.weekday() < 5: 
            valid_dates.append(future_date.strftime('%Y-%m-%d'))
    return valid_dates

def run():
    bot = MouratoglouSniper(EMAIL, PASSWORD)
    if not bot.login():
        print("❌ Login initial échoué.")
        return

    dates_to_check = get_target_dates()
    print(f"📅 Dates ciblées : {', '.join(dates_to_check)}")

    total_success = 0
    
    for current_target in dates_to_check:
        print(f"\n--- Recherche pour le {current_target} ---")
        start_shoot = time.time()
        
        
        print(f"🔎 Scan {current_target} @ {TARGET_TIME}...", end='\r')
        slots = bot.find_all_slots(current_target) # On récupère la liste
        if slots:
            for slot in slots: # On tente de réserver chaque terrain trouvé
                if bot.book(slot, current_target):
                    total_success += 1
                    break 
            if total_success >= MAX_BOOKINGS: break
            
           

        if total_success >= MAX_BOOKINGS:
            print(f"\n✅ Nombre maximum de réservations ({MAX_BOOKINGS}) atteint.")
            break

    print(f"\n🏁 Sniper terminé. Réservations effectuées : {total_success}")

if __name__ == "__main__":
    run()

import os
import logging
from typing import Dict, List, Optional
import httpx
from fastmcp import FastMCP
from pydantic import BaseModel
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('/tmp/routes_mcp.log')]
)
logger = logging.getLogger(__name__)


class TransitDetails(BaseModel):
    operator: str
    route_number: str
    departure_stop: str
    arrival_stop: str
    departure_time: str
    arrival_time: str
    real_time_data: Optional[Dict] = None


class RouteResponse(BaseModel):
    routes: List[List[TransitDetails]]


mcp = FastMCP("Transit Routes Israel")


@mcp.tool()
async def get_route(origin: str, destination: str) -> RouteResponse:
    """Get real-time transit routes between two addresses in Israel"""
    
    # Step 1: Call Google Routes API
    google_routes = await call_google_routes_api(origin, destination)
    
    # Step 2: Extract origin city from geocoding results
    origin_city = await extract_city_from_geocoding(google_routes)
    
    # Step 3: Extract transit details and get real-time data
    routes_with_realtime = []
    
    # Add defensive check for google_routes structure
    if not isinstance(google_routes, dict):
        logger.error(f"Expected dict for google_routes but got {type(google_routes)}: {google_routes}")
        return RouteResponse(routes=[])
    
    routes = google_routes.get("routes", [])
    if not isinstance(routes, list):
        logger.error(f"Expected list for routes but got {type(routes)}: {routes}")
        return RouteResponse(routes=[])
    
    # Limit number of routes to process (configurable via env var)
    max_routes = int(os.getenv("MAX_ROUTES", "2"))
    routes = routes[:max_routes]
    logger.info(f"Processing {len(routes)} routes (max: {max_routes})")
    
    for route in routes:
        route_details = []
        
        if not isinstance(route, dict):
            logger.warning(f"Expected dict for route but got {type(route)}")
            continue
        
        legs = route.get("legs", [])
        if not isinstance(legs, list):
            logger.warning(f"Expected list for legs but got {type(legs)}")
            continue
        
        for leg in legs:
            if not isinstance(leg, dict):
                logger.warning(f"Expected dict for leg but got {type(leg)}")
                continue
                
            steps = leg.get("steps", [])
            if not isinstance(steps, list):
                logger.warning(f"Expected list for steps but got {type(steps)}")
                continue
            
            is_first_transit_step = True
            for step in steps:
                if not isinstance(step, dict):
                    logger.warning(f"Expected dict for step but got {type(step)}")
                    continue
                    
                if "transitDetails" in step:
                    # Only get real-time data for the first transit step in each route
                    get_realtime = is_first_transit_step
                    transit_detail = await process_transit_step(step["transitDetails"], origin_city, get_realtime)
                    if transit_detail:
                        route_details.append(transit_detail)
                    is_first_transit_step = False
        
        if route_details:
            routes_with_realtime.append(route_details)
    
    return RouteResponse(routes=routes_with_realtime)


async def call_google_routes_api(origin: str, destination: str) -> Dict:
    """Call Google Routes API for transit directions"""
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    
    payload = {
        "languageCode": "he-IL",
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "TRANSIT",
        "computeAlternativeRoutes": True,
        "transitPreferences": {
            "routingPreference": "LESS_WALKING",
            "allowedTravelModes": ["BUS", "TRAIN", "LIGHT_RAIL", "RAIL"]
        }
    }
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is required")
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.legs.steps.transitDetails,geocodingResults"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


async def extract_city_from_geocoding(google_routes: Dict) -> Optional[str]:
    """Extract city name from Google Routes geocoding results using Places API"""
    try:
        geocoding_results = google_routes.get("geocodingResults", {})
        if not isinstance(geocoding_results, dict):
            return None
        
        origin = geocoding_results.get("origin", {})
        place_id = origin.get("placeId") if isinstance(origin, dict) else None
        
        if not place_id:
            return None
        
        # Call Google Places API to get city name
        city = await get_city_from_place_id(place_id)
        return city
        
    except Exception as e:
        logger.error(f"Error extracting city from geocoding: {e}")
        return None


async def get_city_from_place_id(place_id: str) -> Optional[str]:
    """Get city name from Google Places API using place_id"""
    try:
        url = f"https://places.googleapis.com/v1/places/{place_id}"
        
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "addressComponents"
        }
        
        params = {
            "languageCode": "he"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Extract city from addressComponents
            address_components = data.get("addressComponents", [])
            for component in address_components:
                types = component.get("types", [])
                if "locality" in types:
                    return component.get("longText", "")
            return None
            
    except Exception as e:
        logger.error(f"Error getting city from place_id: {e}")
        return None


async def process_transit_step(transit_details: Dict, origin_city: str = None, get_realtime: bool = True) -> Optional[TransitDetails]:
    """Process a single transit step and enrich with real-time data"""
    
    transit_line = transit_details.get("transitLine", {})
    stop_details = transit_details.get("stopDetails", {})
    
    # Extract basic info
    agencies = transit_line.get("agencies", [])
    operator = agencies[0].get("name", "") if agencies else ""
    route_number = transit_line.get("nameShort", "")
    
    departure_stop_info = stop_details.get("departureStop", {})
    arrival_stop_info = stop_details.get("arrivalStop", {})
    
    departure_stop = departure_stop_info.get("name", "")
    arrival_stop = arrival_stop_info.get("name", "")
    
    # Extract times from localizedValues field
    # The localized times are in transit_details.localizedValues, not in stop_details
    localized_values = transit_details.get("localizedValues", {})
    
    # Extract departure time
    departure_time = ""
    departure_time_localized = localized_values.get("departureTime", {})
    if departure_time_localized and isinstance(departure_time_localized, dict):
        time_obj = departure_time_localized.get("time", {})
        if isinstance(time_obj, dict):
            departure_time = time_obj.get("text", "")
    
    # Extract arrival time  
    arrival_time = ""
    arrival_time_localized = localized_values.get("arrivalTime", {})
    if arrival_time_localized and isinstance(arrival_time_localized, dict):
        time_obj = arrival_time_localized.get("time", {})
        if isinstance(time_obj, dict):
            arrival_time = time_obj.get("text", "")
    
    # Fallback to ISO timestamps if localized times not found
    if not departure_time:
        departure_time_raw = stop_details.get("departureTime", "")
        departure_time = departure_time_raw if isinstance(departure_time_raw, str) else ""
    
    if not arrival_time:
        arrival_time_raw = stop_details.get("arrivalTime", "")
        arrival_time = arrival_time_raw if isinstance(arrival_time_raw, str) else ""
    
    # Get real-time data from curlbus only if requested
    real_time_data = None
    if get_realtime:
        real_time_data = await get_curlbus_data(operator, route_number, departure_stop_info, arrival_stop_info, origin_city)
    
    return TransitDetails(
        operator=operator,
        route_number=route_number,
        departure_stop=departure_stop,
        arrival_stop=arrival_stop,
        departure_time=departure_time,
        arrival_time=arrival_time,
        real_time_data=real_time_data
    )


async def get_curlbus_data(operator: str, route_number: str, departure_stop_info: Dict, arrival_stop_info: Dict = None, origin_city: str = None) -> Optional[Dict]:
    """Get real-time data from curlbus API using GTFS stop code"""
    import asyncio
    
    try:
        departure_name = departure_stop_info.get("name", "")
        if not origin_city:
            return {"status": "no_realtime", "reason": "No city information available"}
        
        # Wrap the entire curlbus lookup in a timeout
        try:
            # Find stop code using GTFS API based on city and station name
            stop_code = await asyncio.wait_for(
                find_stop_code_from_gtfs(origin_city, departure_name), 
                timeout=8.0
            )
            
            if not stop_code:
                return {"status": "no_realtime", "reason": f"Stop not found in GTFS data for {departure_name}"}
            
            # Get real-time data with timeout, filtered by route number
            realtime_data = await asyncio.wait_for(
                get_stop_realtime_data(stop_code, route_number),
                timeout=3.0
            )
            return realtime_data
            
        except asyncio.TimeoutError:
            return {"status": "no_realtime", "reason": "curlbus timeout"}
            
    except Exception as e:
        logger.error(f"Error getting curlbus data: {e}")
        return {"status": "no_realtime", "reason": str(e)}


async def get_stop_realtime_data(stop_code: str, route_number: str) -> Dict:
    """Get real-time data for a specific stop code, filtered by route number"""
    url = f"https://curlbus.app/{stop_code}"
    
    timeout = httpx.Timeout(2.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url)
        response.raise_for_status()
        text_data = response.text
        
        realtime_info = parse_curlbus_realtime_text(text_data, route_number)
        realtime_info["status"] = "success"
        return realtime_info


def parse_curlbus_realtime_text(text_content: str, route_number: str) -> Dict:
    """Parse curlbus real-time text response, filtered by route number"""
    import re
    
    lines = text_content.split('\n')
    
    arrivals = []
    
    for line in lines:
        table_match = re.search(r'│\s*(.+?)\s*│\s*(.+?)\s*│\s*(.+?)\s*│\s*(.+?)\s*│', line)
        if table_match:
            route_cell = table_match.group(1).strip()
            time_cell = table_match.group(4).strip()
            
            if route_cell == route_number:
                
                if time_cell and time_cell not in ['', '│']:
                    if 'now' in time_cell.lower():
                        arrivals.append("now")
                        minute_match = re.search(r'(\d+)m', time_cell)
                        if minute_match:
                            arrivals.append(f"{minute_match.group(1)} min")
                    elif re.search(r'\d+\s*m(?:in)?', time_cell.lower()):
                        minute_matches = re.findall(r'(\d+)\s*m(?:in)?', time_cell.lower())
                        for minutes in minute_matches:
                            arrivals.append(f"{minutes} min")
                    elif re.search(r'\d{1,2}:\d{2}', time_cell):
                        time_matches = re.findall(r'(\d{1,2}:\d{2})', time_cell)
                        arrivals.extend(time_matches)
                    elif ',' in time_cell:
                        parts = time_cell.split(',')
                        for part in parts:
                            part = part.strip()
                            if 'now' in part.lower():
                                arrivals.append("now")
                            elif re.search(r'\d+\s*m(?:in)?', part.lower()):
                                minute_matches = re.findall(r'(\d+)\s*m(?:in)?', part.lower())
                                for minutes in minute_matches:
                                    arrivals.append(f"{minutes} min")
    
    seen = set()
    unique_arrivals = []
    for arrival in arrivals:
        if arrival not in seen:
            seen.add(arrival)
            unique_arrivals.append(arrival)
    
    final_arrivals = unique_arrivals[:5]
    
    return {
        "arrivals": final_arrivals,
        "next_arrival": final_arrivals[0] if final_arrivals else None
    }


def get_last_thursday_or_week_before() -> str:
    today = datetime.now()
    current_day = today.weekday()
    
    if current_day == 3:
        target_date = today - timedelta(days=7)
    else:
        days_to_subtract = current_day - 3 if current_day > 3 else current_day + 4
        target_date = today - timedelta(days=days_to_subtract)
    
    return target_date.strftime('%Y-%m-%d')


async def fetch_gtfs_stops(city: str, date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
    base_url = 'https://open-bus-stride-api.hasadna.org.il/gtfs_stops/list'
    target_date = date_from or get_last_thursday_or_week_before()
    end_date = date_to or target_date
    
    params = {
        'city': city,
        'date_from': target_date,
        'date_to': end_date,
        'get_count': False,
        'limit': 500000
    }
    
    try:
        timeout = httpx.Timeout(5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f'Error fetching GTFS stops: {e}')
        raise


def find_stop_code_by_name(stops: List[Dict], station_name: str) -> Optional[str]:
    if not isinstance(stops, list):
        return None
    
    station_name_lower = station_name.strip().lower()
    
    for stop in stops:
        if stop.get('name') and stop['name'].strip().lower() == station_name_lower:
            return str(stop.get('code'))
    
    for stop in stops:
        if stop.get('name') and station_name_lower in stop['name'].lower():
            return str(stop.get('code'))
    
    for stop in stops:
        if stop.get('name') and stop['name'].lower() in station_name_lower:
            return str(stop.get('code'))
    
    return None


async def find_stop_code_from_gtfs(city: str, station_name: str) -> Optional[str]:
    try:
        stops_data = await fetch_gtfs_stops(city)
        if not stops_data:
            return None
        return find_stop_code_by_name(stops_data, station_name)
    except Exception as e:
        logger.error(f"Error finding stop code from GTFS API: {e}")
        return None


def main():
    mcp.run()

if __name__ == "__main__":
    main()
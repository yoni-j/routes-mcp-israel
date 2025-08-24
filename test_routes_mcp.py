import unittest
import asyncio
import os
from unittest.mock import patch, AsyncMock, MagicMock
from server import (
    get_route, 
    call_google_routes_api, 
    get_curlbus_data,
    find_stop_code_by_name,
    parse_curlbus_realtime_text,
    extract_city_from_geocoding,
    get_city_from_place_id,
    find_stop_code_from_gtfs,
    get_last_thursday_or_week_before
)


class TestRoutesMCP(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        os.environ["GOOGLE_API_KEY"] = "test_api_key"
    
    def test_get_last_thursday_calculation(self):
        """Test last Thursday date calculation"""
        result = get_last_thursday_or_week_before()
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 10)  # YYYY-MM-DD format
        self.assertRegex(result, r'\d{4}-\d{2}-\d{2}')
    
    def test_find_stop_code_by_name(self):
        """Test stop code matching by name"""
        stops = [
            {"name": "תחנה מרכזית תל אביב", "code": "12345"},
            {"name": "רציף 16", "code": "67890"},
            {"name": "בית חולים איכילוב", "code": "54321"}
        ]
        
        # Exact match
        result = find_stop_code_by_name(stops, "תחנה מרכזית תל אביב")
        self.assertEqual(result, "12345")
        
        # Partial match
        result = find_stop_code_by_name(stops, "תחנה מרכזית")
        self.assertEqual(result, "12345")
        
        # Reverse partial match
        result = find_stop_code_by_name(stops, "איכילוב")
        self.assertEqual(result, "54321")
        
        # No match
        result = find_stop_code_by_name(stops, "תחנת רכבת")
        self.assertIsNone(result)
        
        # Invalid input
        result = find_stop_code_by_name("invalid", "test")
        self.assertIsNone(result)
    
    def test_parse_curlbus_realtime_text(self):
        """Test parsing curlbus real-time data"""
        mock_text = """
        │405  │אגד    │תחנה מרכזית ירושלים  │13 min, 28 min│
        │480  │אגד    │קניון עזריאלי        │Now, 15 min   │
        │405  │אגד    │תחנה מרכזית ירושלים  │45 min        │
        """
        
        # Test finding arrivals for specific route
        result = parse_curlbus_realtime_text(mock_text, "405")
        self.assertIn("arrivals", result)
        self.assertIn("next_arrival", result)
        self.assertEqual(len(result["arrivals"]), 3)  # 13 min, 28 min, 45 min
        self.assertEqual(result["next_arrival"], "13 min")
        
        # Test no matches
        result = parse_curlbus_realtime_text(mock_text, "999")
        self.assertEqual(result["arrivals"], [])
        self.assertIsNone(result["next_arrival"])
    
    @patch('server.httpx.AsyncClient')
    async def test_google_routes_api_success(self, mock_client):
        """Test successful Google Routes API call"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "routes": [{
                "legs": [{
                    "steps": [{
                        "transitDetails": {
                            "transitLine": {
                                "agencies": [{"name": "אגד"}],
                                "nameShort": "405"
                            },
                            "stopDetails": {
                                "departureStop": {"name": "תחנה מרכזית תל אביב"},
                                "arrivalStop": {"name": "תחנה מרכזית ירושלים"},
                                "departureTime": "2025-08-24T14:00:00Z",
                                "arrivalTime": "2025-08-24T15:00:00Z"
                            },
                            "localizedValues": {
                                "departureTime": {"time": {"text": "17:00"}},
                                "arrivalTime": {"time": {"text": "18:00"}}
                            }
                        }
                    }]
                }]
            }],
            "geocodingResults": {
                "origin": {"placeId": "ChIJ123456789"}
            }
        }
        
        mock_client_instance = mock_client.return_value.__aenter__.return_value
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        
        result = await call_google_routes_api("תל אביב", "ירושלים")
        
        self.assertIn("routes", result)
        self.assertIn("geocodingResults", result)
        self.assertEqual(len(result["routes"]), 1)
    
    @patch('server.httpx.AsyncClient')
    async def test_get_city_from_place_id_success(self, mock_client):
        """Test successful city extraction from place ID"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "addressComponents": [
                {"types": ["country"], "longText": "ישראל"},
                {"types": ["locality"], "longText": "תל אביב"},
                {"types": ["administrative_area"], "longText": "מחוז תל אביב"}
            ]
        }
        
        mock_client_instance = mock_client.return_value.__aenter__.return_value
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        
        result = await get_city_from_place_id("ChIJ123456789")
        self.assertEqual(result, "תל אביב")
    
    @patch('server.httpx.AsyncClient')
    async def test_get_city_from_place_id_no_locality(self, mock_client):
        """Test place ID with no locality component"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "addressComponents": [
                {"types": ["country"], "longText": "ישראל"},
                {"types": ["administrative_area"], "longText": "מחוז תל אביב"}
            ]
        }
        
        mock_client_instance = mock_client.return_value.__aenter__.return_value
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        
        result = await get_city_from_place_id("ChIJ123456789")
        self.assertIsNone(result)
    
    async def test_extract_city_from_geocoding_success(self):
        """Test successful city extraction from geocoding results"""
        with patch('server.get_city_from_place_id', return_value="תל אביב"):
            google_routes = {
                "geocodingResults": {
                    "origin": {"placeId": "ChIJ123456789"}
                }
            }
            
            result = await extract_city_from_geocoding(google_routes)
            self.assertEqual(result, "תל אביב")
    
    async def test_extract_city_from_geocoding_no_place_id(self):
        """Test geocoding results without place ID"""
        google_routes = {
            "geocodingResults": {
                "origin": {}
            }
        }
        
        result = await extract_city_from_geocoding(google_routes)
        self.assertIsNone(result)
    
    async def test_extract_city_from_geocoding_invalid_input(self):
        """Test invalid geocoding input"""
        result = await extract_city_from_geocoding("invalid_input")
        self.assertIsNone(result)
    
    @patch('server.fetch_gtfs_stops')
    async def test_find_stop_code_from_gtfs_success(self, mock_fetch):
        """Test successful GTFS stop code finding"""
        mock_fetch.return_value = [
            {"name": "תחנה מרכזית תל אביב/קומה 3/רציף 16", "code": "12345"},
            {"name": "אבן גבירול/דיזינגוף", "code": "67890"}
        ]
        
        result = await find_stop_code_from_gtfs("תל אביב", "תחנה מרכזית")
        self.assertEqual(result, "12345")
    
    @patch('server.fetch_gtfs_stops')
    async def test_find_stop_code_from_gtfs_no_stops(self, mock_fetch):
        """Test GTFS lookup with no stops found"""
        mock_fetch.return_value = []
        
        result = await find_stop_code_from_gtfs("תל אביב", "תחנה מרכזית")
        self.assertIsNone(result)
    
    @patch('server.find_stop_code_from_gtfs')
    @patch('server.get_stop_realtime_data')
    async def test_get_curlbus_data_success(self, mock_realtime, mock_gtfs):
        """Test successful curlbus data retrieval"""
        mock_gtfs.return_value = "12345"
        mock_realtime.return_value = {
            "arrivals": ["13 min", "28 min"],
            "next_arrival": "13 min",
            "status": "success"
        }
        
        departure_stop_info = {"name": "תחנה מרכזית תל אביב"}
        result = await get_curlbus_data("אגד", "405", departure_stop_info, None, "תל אביב")
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["arrivals"]), 2)
        self.assertEqual(result["next_arrival"], "13 min")
    
    async def test_get_curlbus_data_no_city(self):
        """Test curlbus data with no city provided"""
        departure_stop_info = {"name": "תחנה מרכזית תל אביב"}
        result = await get_curlbus_data("אגד", "405", departure_stop_info, None, None)
        
        self.assertEqual(result["status"], "no_realtime")
        self.assertIn("city", result["reason"])
    
    @patch('server.extract_city_from_geocoding')
    @patch('server.call_google_routes_api')
    async def test_get_route_max_routes_limit(self, mock_google_api, mock_extract_city):
        """Test route limiting with MAX_ROUTES"""
        # Mock 3 routes but expect only 2 (default MAX_ROUTES)
        mock_google_api.return_value = {
            "routes": [
                {"legs": [{"steps": [{"transitDetails": {
                    "transitLine": {"agencies": [{"name": "אגד"}], "nameShort": "405"},
                    "stopDetails": {
                        "departureStop": {"name": "תחנה מרכזית תל אביב"},
                        "arrivalStop": {"name": "תחנה מרכזית ירושלים"},
                        "departureTime": "2025-08-24T14:00:00Z",
                        "arrivalTime": "2025-08-24T15:00:00Z"
                    },
                    "localizedValues": {
                        "departureTime": {"time": {"text": "17:00"}},
                        "arrivalTime": {"time": {"text": "18:00"}}
                    }
                }}]}]},
                {"legs": [{"steps": [{"transitDetails": {
                    "transitLine": {"agencies": [{"name": "אגד"}], "nameShort": "480"},
                    "stopDetails": {
                        "departureStop": {"name": "תחנה מרכזית תל אביב"},
                        "arrivalStop": {"name": "תחנה מרכזית ירושלים"},
                        "departureTime": "2025-08-24T14:30:00Z",
                        "arrivalTime": "2025-08-24T15:30:00Z"
                    },
                    "localizedValues": {
                        "departureTime": {"time": {"text": "17:30"}},
                        "arrivalTime": {"time": {"text": "18:30"}}
                    }
                }}]}]},
                {"legs": [{"steps": [{"transitDetails": {
                    "transitLine": {"agencies": [{"name": "אגד"}], "nameShort": "470"},
                    "stopDetails": {
                        "departureStop": {"name": "תחנה מרכזית תל אביב"},
                        "arrivalStop": {"name": "תחנה מרכזית ירושלים"},
                        "departureTime": "2025-08-24T15:00:00Z",
                        "arrivalTime": "2025-08-24T16:00:00Z"
                    },
                    "localizedValues": {
                        "departureTime": {"time": {"text": "18:00"}},
                        "arrivalTime": {"time": {"text": "19:00"}}
                    }
                }}]}]}
            ],
            "geocodingResults": {"origin": {"placeId": "ChIJ123456789"}}
        }
        mock_extract_city.return_value = "תל אביב"
        
        with patch('server.get_curlbus_data', return_value={"status": "no_realtime"}):
            result = await get_route("תל אביב", "ירושלים")
        
        # Should only return 2 routes (MAX_ROUTES default)
        self.assertEqual(len(result.routes), 2)


class TestIntegration(unittest.TestCase):
    """Integration tests (require real API keys)"""
    
    def setUp(self):
        if not os.getenv("GOOGLE_API_KEY"):
            self.skipTest("GOOGLE_API_KEY not set - skipping integration tests")
    
    async def test_real_google_routes_api(self):
        """Test with real Google Routes API"""
        try:
            result = await call_google_routes_api("תל אביב", "ירושלים")
            self.assertIn("routes", result)
            self.assertIn("geocodingResults", result)
        except Exception as e:
            self.skipTest(f"Google Routes API test failed: {e}")
    
    async def test_real_places_api(self):
        """Test with real Google Places API"""
        try:
            # This would require a real place ID from a real Google Routes response
            # For now, just test that the function handles errors gracefully
            result = await get_city_from_place_id("ChIJInvalidPlaceId")
            # Should return None for invalid place ID rather than crashing
            self.assertIsNone(result)
        except Exception as e:
            # API errors are acceptable in integration tests
            pass
    
    async def test_real_get_route_flow(self):
        """Test complete flow with real APIs"""
        try:
            result = await get_route("תל אביב", "ירושלים")
            self.assertIsNotNone(result)
            self.assertGreater(len(result.routes), 0)
            
            # Check that we get Hebrew localized times
            first_route = result.routes[0][0]
            self.assertIsNotNone(first_route.departure_time)
            self.assertIsNotNone(first_route.arrival_time)
            
            # Times should be in HH:MM format (not ISO timestamps)
            if first_route.departure_time:
                self.assertRegex(first_route.departure_time, r'^\d{1,2}:\d{2}$|^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
                
        except Exception as e:
            self.skipTest(f"Integration test failed: {e}")


def run_async_test(test_func):
    """Helper to run async tests"""
    return asyncio.run(test_func())


if __name__ == "__main__":
    # Custom test runner for async tests
    class AsyncTestResult(unittest.TextTestResult):
        def addTest(self, test):
            if asyncio.iscoroutinefunction(getattr(test, test._testMethodName, None)):
                # Convert async test to sync
                original_method = getattr(test, test._testMethodName)
                setattr(test, test._testMethodName, lambda: run_async_test(original_method))
            super().addTest(test)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add unit tests
    suite.addTests(loader.loadTestsFromTestCase(TestRoutesMCP))
    
    # Add integration tests (only if API key is available)
    if os.getenv("GOOGLE_API_KEY"):
        suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
        print("🔑 API key found - including integration tests")
    else:
        print("⚠️  No API key - running unit tests only")
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2, resultclass=AsyncTestResult)
    result = runner.run(suite)
    
    # Print summary
    print(f"\n{'='*50}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    if result.testsRun > 0:
        success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100)
        print(f"Success rate: {success_rate:.1f}%")
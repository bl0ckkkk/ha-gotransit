"""Realistic API response fixtures based on OpenMetrolinx documented schemas."""

# Stop/NextService — flat Lines array (the schema we fixed to)
NEXT_SERVICE_NORMAL = {
    "Metadata": {"TimeStamp": "2026-06-20 07:08:00", "ErrorCode": "200", "ErrorMessage": "OK"},
    "NextService": {
        "Lines": [
            {
                "StopCode": "BU", "LineCode": "LW", "LineName": "Lakeshore West",
                "ServiceType": "T", "DirectionCode": "LW", "DirectionName": "LW - Union Station",
                "ScheduledDepartureTime": "2026-06-20 07:12:00", "ComputedDepartureTime": "2026-06-20 07:19:00",
                "DepartureStatus": "E", "ScheduledPlatform": "3", "ActualPlatform": "",
                "TripOrder": 2, "TripNumber": "1234", "UpdateTime": "2026-06-20 07:08:00",
                "Status": "S", "Latitude": 43.3140, "Longitude": -79.8530,
            },
            {
                "StopCode": "BU", "LineCode": "LW", "LineName": "Lakeshore West",
                "ServiceType": "T", "DirectionCode": "LW", "DirectionName": "LW - Aldershot GO",
                "ScheduledDepartureTime": "2026-06-20 06:42:00", "ComputedDepartureTime": "2026-06-20 06:42:00",
                "DepartureStatus": "E", "ScheduledPlatform": "1", "ActualPlatform": "",
                "TripOrder": 1, "TripNumber": "1232", "UpdateTime": "2026-06-20 07:08:00",
                "Status": "S", "Latitude": -1.0, "Longitude": -1.0,
            },
        ]
    },
}

# Single line returned as dict, not list (API inconsistency we handle)
NEXT_SERVICE_SINGLE_DICT = {
    "NextService": {
        "Lines": {
            "StopCode": "BU", "LineCode": "LW", "LineName": "Lakeshore West",
            "ServiceType": "T", "DirectionCode": "LW", "DirectionName": "LW - Union Station",
            "ScheduledDepartureTime": "2026-06-20 07:12:00", "ComputedDepartureTime": "2026-06-20 07:12:00",
            "DepartureStatus": "E", "ScheduledPlatform": "2", "ActualPlatform": "",
            "TripOrder": 1, "TripNumber": "5678", "UpdateTime": "2026-06-20 07:08:00",
            "Status": "S", "Latitude": -1.0, "Longitude": -1.0,
        }
    },
}

# Empty (outside service hours)
NEXT_SERVICE_EMPTY = {
    "NextService": {"Lines": []},
}

# Mixed lines — different LineCode should be filtered out
NEXT_SERVICE_MIXED = {
    "NextService": {
        "Lines": [
            {"LineCode": "LE", "LineName": "Lakeshore East", "DirectionName": "LE - Oshawa GO",
             "TripOrder": 1, "TripNumber": "9999",
             "ScheduledDepartureTime": "2026-06-20 07:05:00", "ComputedDepartureTime": "2026-06-20 07:05:00"},
            {"LineCode": "LW", "LineName": "Lakeshore West", "DirectionName": "LW - Union Station",
             "TripOrder": 2, "TripNumber": "1234",
             "ScheduledDepartureTime": "2026-06-20 07:12:00", "ComputedDepartureTime": "2026-06-20 07:19:00"},
        ]
    },
}

# Fleet/Consist/All
CONSIST_ALL = {
    "AllConsists": {
        "Consists": [
            {
                "Number": 42, "CoachCount": 12, "EngineNumber": "560",
                "Lineup": [
                    {"Type": "Locomotive", "Order": 1, "Number": "560"},
                    {"Type": "Coach", "Order": 3, "Number": "2281"},
                    {"Type": "Coach", "Order": 2, "Number": "2194"},
                ],
                "RemainingTrip": [
                    {"Number": "1234", "Corridor": "LW", "StartTime": "07:12",
                     "EndTime": "08:14", "FirstStop": "BU", "LastStop": "UN", "InService": True},
                ],
            },
            {
                "Number": 17, "CoachCount": 10, "EngineNumber": "643",
                "Lineup": [{"Type": "Coach", "Order": 1, "Number": "2000"}],
                "RemainingTrip": {"Number": "9999", "Corridor": "LE"},
            },
        ]
    },
}

CONSIST_NO_MATCH = {
    "AllConsists": {"Consists": [
        {"Number": 1, "CoachCount": 10, "EngineNumber": "999",
         "Lineup": [], "RemainingTrip": [{"Number": "0000"}]},
    ]},
}

# Exceptions/All
EXCEPTIONS_CANCELLED = {
    "Trip": [
        {
            "TripNumber": "1234", "TripName": "LW Express", "IsCancelled": "true",
            "IsOverride": "false",
            "Stop": [
                {"Order": 1, "Code": "BU", "Name": "Burlington", "IsStopping": "false",
                 "IsCancelled": "true", "ActualTime": ""},
            ],
        },
    ],
}

EXCEPTIONS_STOP_SKIPPED = {
    "Trip": [
        {
            "TripNumber": "1234", "TripName": "LW", "IsCancelled": "false",
            "Stop": [
                {"Order": 1, "Code": "BU", "Name": "Burlington", "IsStopping": "false",
                 "IsCancelled": "false", "ActualTime": "07:19"},
            ],
        },
    ],
}

EXCEPTIONS_NONE = {"Trip": []}

# ServiceGuarantee
GUARANTEE_ACTIVE = {
    "Stops": {
        "Stop": [
            {"Code": "BU", "Scope": "Departure", "ReasonEn": "Train delayed 15+ minutes", "ReasonFr": "..."},
            {"Code": "UN", "Scope": "Arrival", "ReasonEn": "Train delayed 15+ minutes", "ReasonFr": "..."},
        ]
    },
}

GUARANTEE_NONE = {"Stops": {"Stop": []}}

# ServiceAlert/All
ALERTS_ALL = {
    "ServiceAlerts": {
        "ServiceAlert": [
            {"AlertId": "ALT-1", "HeaderText": "LW Delays", "DescriptionText": "Mechanical issue",
             "Effect": "SIGNIFICANT_DELAYS", "AffectedLines": "LW", "ActivePeriodStart": "06:30", "ActivePeriodEnd": "09:00"},
            {"AlertId": "ALT-2", "HeaderText": "LE Delays", "DescriptionText": "Signal problem",
             "Effect": "DELAYS", "AffectedLines": "LE", "ActivePeriodStart": "07:00", "ActivePeriodEnd": "08:00"},
            {"AlertId": "ALT-3", "HeaderText": "System notice", "DescriptionText": "Holiday schedule",
             "Effect": "MODIFIED_SERVICE", "AffectedLines": "", "ActivePeriodStart": "00:00", "ActivePeriodEnd": "23:59"},
        ]
    },
}

# Trains — ServiceataGlance/Trains/All (live shape: Trips.Trip)
TRAINS_ALL = {
    "Metadata": {"TimeStamp": "2026-06-21 21:39:58", "ErrorCode": "200", "ErrorMessage": "OK"},
    "Trips": {
        "Trip": [
            {"Cars": "12", "TripNumber": "1234", "LineCode": "LW", "RouteNumber": "LW   ",
             "VariantDir": "E", "Display": "LW - Union Station", "Latitude": 43.38, "Longitude": -79.80,
             "IsInMotion": True, "DelaySeconds": 66, "NextStopCode": "OA", "AtStationCode": None},
            {"Cars": "10", "TripNumber": "9999", "LineCode": "LE", "RouteNumber": "LE   ",
             "VariantDir": "E", "Display": "LE - Oshawa GO", "Latitude": 43.50, "Longitude": -79.40,
             "IsInMotion": False, "DelaySeconds": -1, "NextStopCode": "PI", "AtStationCode": "RO"},
        ]
    },
}

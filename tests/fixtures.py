"""Realistic API response fixtures based on OpenMetrolinx documented schemas."""

# Stop/NextService — flat Lines array (the schema we fixed to)
NEXT_SERVICE_NORMAL = {
    "Metadata": {"TimeStamp": "2026-06-20 07:08:00", "ErrorCode": "200", "ErrorMessage": ""},
    "NextService": {
        "Lines": [
            {
                "StopCode": "BU", "LineCode": "LW", "LineName": "Lakeshore West",
                "ServiceType": "T", "DirectionCode": "E", "DirectionName": "Union Station",
                "ScheduledDepartureTime": "07:12", "ComputedDepartureTime": "07:19",
                "DepartureStatus": "D", "ScheduledPlatform": "2", "ActualPlatform": "3",
                "TripOrder": 2, "TripNumber": "1234", "UpdateTime": "07:08",
                "Status": "Delayed", "Latitude": 43.3841, "Longitude": -79.8053,
            },
            {
                "StopCode": "BU", "LineCode": "LW", "LineName": "Lakeshore West",
                "ServiceType": "T", "DirectionCode": "E", "DirectionName": "Union Station",
                "ScheduledDepartureTime": "06:42", "ComputedDepartureTime": "06:42",
                "DepartureStatus": "O", "ScheduledPlatform": "2", "ActualPlatform": "2",
                "TripOrder": 1, "TripNumber": "1232", "UpdateTime": "07:08",
                "Status": "On Time", "Latitude": 43.40, "Longitude": -79.78,
            },
        ]
    },
}

# Single line returned as dict, not list (API inconsistency we handle)
NEXT_SERVICE_SINGLE_DICT = {
    "NextService": {
        "Lines": {
            "StopCode": "BU", "LineCode": "LW", "LineName": "Lakeshore West",
            "ServiceType": "T", "DirectionCode": "E", "DirectionName": "Union Station",
            "ScheduledDepartureTime": "07:12", "ComputedDepartureTime": "07:12",
            "DepartureStatus": "O", "ScheduledPlatform": "2", "ActualPlatform": "2",
            "TripOrder": 1, "TripNumber": "5678", "UpdateTime": "07:08",
            "Status": "On Time", "Latitude": 43.38, "Longitude": -79.80,
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
            {"LineCode": "LE", "LineName": "Lakeshore East", "TripOrder": 1,
             "TripNumber": "9999", "ScheduledDepartureTime": "07:05",
             "ComputedDepartureTime": "07:05", "DirectionName": "Oshawa"},
            {"LineCode": "LW", "LineName": "Lakeshore West", "TripOrder": 2,
             "TripNumber": "1234", "ScheduledDepartureTime": "07:12",
             "ComputedDepartureTime": "07:19", "DirectionName": "Union Station"},
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

# Trains
TRAINS_ALL = {
    "ServiceataGlance": {
        "Trains": {
            "Train": [
                {"TripNumber": "1234", "LineCode": "LW", "Direction": "Inbound",
                 "Latitude": 43.38, "Longitude": -79.80, "NextStopCode": "OA", "Status": "On Time"},
                {"TripNumber": "9999", "LineCode": "LE", "Direction": "Outbound",
                 "Latitude": 43.50, "Longitude": -79.40, "NextStopCode": "PI", "Status": "On Time"},
            ]
        }
    },
}

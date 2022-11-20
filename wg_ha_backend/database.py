server_interface_ips = [
    "10.0.0.1/24",
    "fdc9:281f:04d7:9ee9::1/112"
]
server_port = 51820
server_public_key = "JxJEVVZffrkRDnY/Cz5DjfFeSoiV1FurHDUCf7Lbuio="
server_endpoint = "116.202.189.178:51820"
clients = [
    {
        "public_key": "inKc45AVOZ45Zu3sYGoJ2uJx+2ePP2pFgNmH+XS2wCA=",
        "allowed_ips": [
            "10.0.0.2/32",
            "fdc9:281f:4d7:9ee9::2/128"
        ],
        "tags": [
            "http",
            "ping"
        ],
        "services": [
            {
                "rules": [
                    {
                        "protocol": "tcp",
                        "ports": [
                            53,
                            5353
                        ]
                    },
                    {
                        "protocol": "udp",
                        "ports": [
                            53,
                            5353
                        ]
                    }
                ],
                "allowed_tags": [
                    "admin",
                    "test"
                ]
            },
            {
                "rules": [
                    {
                        "protocol": "icmp"
                    }
                ],
                "allowed_tags": [
                    "ping"
                ]
            }
        ]
    }
]

server_interface_ips = [
    "10.0.0.1/24",
    "fdc9:281f:04d7:9ee9::1/112"
]
server_private_key = "gG38NoQ9UEYzu5LAHzT3n9Kfk6VJz7iDcHEEuNovIHE="
server_public_key = "SPlAIzq4bkT3IxpFDnxfxACIaLoYMsv/WjxHTr6ZDR8="
server_endpoint = "116.202.189.178:51820"
# clients = []


clients = [
    {
        "private_key": "oAiwQw/ITK9YThiD1JD9QXNLqie7Pyyh01W37Xj46l8=",
        "public_key": "r/Nt83mKnsVxMBU09FZaLUTAudrEodk7oXTdmf/uHyY=",
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

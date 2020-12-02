import argparse
import os
import random
import signal
from socket import *

dns_argument_ip = "8.8.8.8"
TIMEOUT = 2
PORT = 53


def _to_bits(data: bytes):
    return f"{int.from_bytes(data, byteorder='big'):0{len(data) * 8}b}"


def _parse_name(full_data: bytes, start: int):
    data = full_data[start:]
    bits = _to_bits(data)
    if bits.startswith("11"):
        # pointer
        offset = int(bits[2:16], 2)
        name, _ = _parse_name(full_data, offset)
        return name, 2
    else:
        name = []
        position = 0
        size = data[0]

        # ends with marker or pointer
        while size != 0 and not bits[position * 8:].startswith("11"):
            name.append(data[position + 1:position +
                             1 + size].decode("utf-8"))
            position += size + 1
            size = data[position]

        if size != 0:
            # ends with pointer
            offset = int(bits[position * 8 + 2:position * 8 + 16], 2)
            end, _ = _parse_name(full_data, offset)
            if isinstance(end, list):
                name.extend(end)
            else:
                name.append(end)
            position += 1

        return ".".join(name), position + 1


class DnsQuery:
    def __init__(self, data_address, start=0):
        if isinstance(data_address, bytes):
            full_data = data_address
            self.name, offset = _parse_name(full_data, start)
            data = full_data[start + offset:]
            self.qtype = int.from_bytes(data[0:2], byteorder="big")
            self.qclass = int.from_bytes(data[2:4], byteorder="big")
            self._size = offset + 4

        elif isinstance(data_address, str):
            self.name = data_address
            self.qtype = 1
            self.qclass = 1
            self._size = len(self.name) + 5
        else:
            raise ValueError("Data has invalid type")

    def raw(self):
        raw_str = str()
        for part in self.name.split("."):
            part_bytes = "".join("{:08b}".format(ord(c)) for c in part)
            raw_str += f"{len(part):08b}"
            raw_str += part_bytes
        raw_str += str().zfill(8)

        for value in [self.qtype, self.qclass]:
            raw_str += f"{value:016b}"

        size = len(raw_str) // 8
        return int(raw_str, 2).to_bytes(size, byteorder="big")

    def __str__(self):
        string = str()
        string += "    Name: " + str(self.name) + "\n"
        string += "   Qtype: " + str(self.qtype) + "\n"
        string += "  Qclass: " + str(self.qclass)
        return string

    def __len__(self):
        return self._size


class DnsResponse:
    def __init__(self, full_data: bytes, start: int):
        self.name, offset = _parse_name(full_data, start)
        self._size = offset
        data = full_data[start + offset:]
        self.type = int.from_bytes(data[0:2], byteorder="big")
        self.rclass = int.from_bytes(data[2:4], byteorder="big")
        self.ttl = int.from_bytes(data[4:8], byteorder="big")
        self.rdlength = int.from_bytes(data[8:10], byteorder="big")
        self.rdata = data[10:10 + self.rdlength]
        self._size += 10 + self.rdlength

    def __str__(self):
        string = str()
        string += "    Name: " + str(self.name) + "\n"
        string += "    Type: " + str(self.type) + "\n"
        string += "   Class: " + str(self.rclass) + "\n"
        string += "     TTL: " + str(self.ttl) + "\n"
        string += "Rdlength: " + str(self.rdlength) + "\n"
        string += "   Rdata: " + str(self.rdata)
        # for ip in self.rdata:
        # string += "Ip: " + inet_ntop(AF_INET, ip)
        return string

    def __len__(self):
        return self._size


class DnsPacket:
    def _packet_from_bytes(self, data: bytes):
        size = len(data) * 8
        bits = _to_bits(data)

        self.id = int(bits[0:16], 2)
        self.qr = int(bits[16], 2)
        self.opcode = int(bits[17:21], 2)
        self.aa, self.tc, self.rd, self.ra = (
            int(bits[i], 2) for i in range(21, 25))

        self.z = int(bits[25:28], 2)
        self.rcode = int(bits[28: 32], 2)
        self.qdcount, self.ancount, self.nscount, self.arcount = [
            int(bits[32 + i * 16:32 + (i + 1) * 16], 2) for i in range(0, 4)]

    def __init__(self, raw: bytes = None):
        self.questions = []
        self.answers = []
        if raw is not None:
            self._packet_from_bytes(raw)

        else:
            self.id = random.randint(0, 2 ** 16)
            self.qr = 0
            self.opcode = 0
            self.aa = 0
            self.tc = 0
            self.rd = 1
            self.ra = 0
            self.z = 0
            self.rcode = 0

            self.qdcount = 1
            self.ancount = 0
            self.nscount = 0
            self.arcount = 0

    def __len__(self):
        return 12

    def __str__(self):
        string = str()
        string += "      ID: " + str(hex(self.id)) + "\n"
        string += "      QR: " + str(self.qr) + "\n"
        string += "  Opcode: " + str(self.opcode) + "\n"
        string += "      AA: " + str(self.aa) + "\n"
        string += "      TC: " + str(self.tc) + "\n"
        string += "      RD: " + str(self.rd) + "\n"
        string += "      RA: " + str(self.ra) + "\n"
        string += "       Z: " + str(self.z) + "\n"
        string += "   Rcode: " + str(self.rcode) + "\n"
        string += " Qdcount: " + str(self.qdcount) + "\n"
        string += " Ancount: " + str(self.ancount) + "\n"
        string += " Nscount: " + str(self.nscount) + "\n"
        string += " Arcount: " + str(self.arcount)

        for question in self.questions:
            string += "\n\n====== QUERY ======\n"
            string += str(question)

        for answer in self.answers:
            string += "\n\n====== ANSWER ======\n"
            string += str(answer)

        return string

    def raw(self):
        raw_str = str()
        raw_str += f"{self.id:016b}"
        raw_str += f"{self.qr:01b}"
        raw_str += f"{self.opcode:04b}"

        for value in (self.aa, self.tc, self.rd, self.ra):
            raw_str += f"{value:01b}"

        raw_str += f"{self.z:03b}"
        raw_str += f"{self.rcode:04b}"

        for count in (self.qdcount, self.ancount, self.nscount, self.arcount):
            raw_str += f"{count:016b}"

        questions_raw = b"".join(q.raw() for q in self.questions)

        size = len(raw_str) // 8
        return int(raw_str, 2).to_bytes(size, byteorder="big") + questions_raw


def get_dns_from_config():
    conf = "/etc/resolv.conf"
    if not os.path.exists(conf):
        return None

    with open(conf, "r") as resolve:
        for line in resolve:
            line = line.strip()
            if line.startswith("#"):
                continue
            dns_ip = line.split()[-1]
            yield dns_ip


def _send_query(ip: str, name: str):
    if len(ip) == 0:
        return None

    query = DnsPacket()
    query.questions.append(DnsQuery(name))

    with socket(AF_INET, SOCK_DGRAM) as s:
        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        s.settimeout(TIMEOUT)
        s.bind(('', PORT))
        s.sendto(query.raw(), (ip, PORT))

        while True:
            bytes, _ = s.recvfrom(1024)
            response = DnsPacket(bytes)

            # Response to another client or from a client
            if response.qr != 1 or response.id != query.id:
                continue

            # Nothing received till timeout
            if bytes == 0:
                return None

            offset = len(response)
            for i in range(response.qdcount):
                query = DnsQuery(bytes, offset)
                offset += len(query)
                response.questions.append(query)

            for i in range(response.ancount):
                answer = DnsResponse(bytes, offset)
                offset += len(answer)
                response.answers.append(answer)

            return response


def resolve_name(name: str):
    dns_ips = [dns_argument_ip]
    # dns_ips.extend(get_dns_from_config())

    for dns_ip in dns_ips:
        packet = _send_query(dns_ip, name)
        # if packet is not None:
        # return inet_ntop(AF_INET, packet.data.ip)
        print(packet)
    return None


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *args: exit(0))
    # while True:
    # try:
    # cite_name = input()
    resolve_name("www.northeastern.edu")
    # except EOFError:
    # break
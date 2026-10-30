"""Authenticode signatures, checked with the Windows API (WinVerifyTrust) (Windows only).

The app asks Windows directly rather than starting PowerShell: a background app that runs hidden
scripts is what antivirus heuristics flag.
"""

from __future__ import annotations

import ctypes
import uuid
from ctypes import wintypes
from pathlib import Path

WINTRUST_ACTION_GENERIC_VERIFY_V2 = "00AAC56B-CD44-11D0-8CC2-00C04FC295EE"
WTD_UI_NONE = 2
WTD_REVOKE_NONE = 0
WTD_CHOICE_FILE = 1
WTD_STATEACTION_VERIFY = 1
WTD_STATEACTION_CLOSE = 2
CERT_NAME_RDN_TYPE = 2
CERT_X500_NAME_STR = 3
CERT_NAME_STR_REVERSE_FLAG = 0x02000000  # "CN=…, O=…, C=…", the order PowerShell and certmgr show


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class _FileInfo(ctypes.Structure):  # WINTRUST_FILE_INFO
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pcwszFilePath", wintypes.LPCWSTR),
        ("hFile", wintypes.HANDLE),
        ("pgKnownSubject", ctypes.c_void_p),
    ]


class _TrustData(ctypes.Structure):  # WINTRUST_DATA
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pPolicyCallbackData", ctypes.c_void_p),
        ("pSIPClientData", ctypes.c_void_p),
        ("dwUIChoice", wintypes.DWORD),
        ("fdwRevocationChecks", wintypes.DWORD),
        ("dwUnionChoice", wintypes.DWORD),
        ("pFile", ctypes.POINTER(_FileInfo)),
        ("dwStateAction", wintypes.DWORD),
        ("hWVTStateData", wintypes.HANDLE),
        ("pwszURLReference", wintypes.LPWSTR),
        ("dwProvFlags", wintypes.DWORD),
        ("dwUIContext", wintypes.DWORD),
        ("pSignatureSettings", ctypes.c_void_p),
    ]


class _ProviderCert(ctypes.Structure):  # the start of CRYPT_PROVIDER_CERT
    _fields_ = [("cbStruct", wintypes.DWORD), ("pCert", ctypes.c_void_p)]


def _api():
    wintrust, crypt32 = ctypes.WinDLL("wintrust"), ctypes.WinDLL("crypt32")
    wintrust.WinVerifyTrust.argtypes = [wintypes.HWND, ctypes.POINTER(_GUID), ctypes.POINTER(_TrustData)]
    wintrust.WinVerifyTrust.restype = wintypes.LONG
    wintrust.WTHelperProvDataFromStateData.argtypes = [wintypes.HANDLE]
    wintrust.WTHelperProvDataFromStateData.restype = ctypes.c_void_p
    wintrust.WTHelperGetProvSignerFromChain.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    wintrust.WTHelperGetProvSignerFromChain.restype = ctypes.c_void_p
    wintrust.WTHelperGetProvCertFromChain.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    wintrust.WTHelperGetProvCertFromChain.restype = ctypes.POINTER(_ProviderCert)
    crypt32.CertGetNameStringW.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD
    ]
    crypt32.CertGetNameStringW.restype = wintypes.DWORD
    return wintrust, crypt32


def _subject(crypt32, cert: int) -> str | None:
    kind = wintypes.DWORD(CERT_X500_NAME_STR | CERT_NAME_STR_REVERSE_FLAG)
    size = crypt32.CertGetNameStringW(cert, CERT_NAME_RDN_TYPE, 0, ctypes.byref(kind), None, 0)
    buf = ctypes.create_unicode_buffer(size)
    crypt32.CertGetNameStringW(cert, CERT_NAME_RDN_TYPE, 0, ctypes.byref(kind), buf, size)
    return buf.value or None


def signer(path: Path) -> str | None:
    """The certificate subject of a valid Authenticode signature on ``path``, else None."""
    wintrust, crypt32 = _api()
    action = _GUID.from_buffer_copy(uuid.UUID(WINTRUST_ACTION_GENERIC_VERIFY_V2).bytes_le)
    file = _FileInfo(cbStruct=ctypes.sizeof(_FileInfo), pcwszFilePath=str(path))
    data = _TrustData(
        cbStruct=ctypes.sizeof(_TrustData),
        dwUIChoice=WTD_UI_NONE,
        fdwRevocationChecks=WTD_REVOKE_NONE,
        dwUnionChoice=WTD_CHOICE_FILE,
        pFile=ctypes.pointer(file),
        dwStateAction=WTD_STATEACTION_VERIFY,
    )
    status = wintrust.WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(data))
    try:
        if status != 0:
            return None
        provider = wintrust.WTHelperProvDataFromStateData(data.hWVTStateData)
        signer_info = wintrust.WTHelperGetProvSignerFromChain(provider, 0, False, 0) if provider else None
        cert = wintrust.WTHelperGetProvCertFromChain(signer_info, 0) if signer_info else None
        return _subject(crypt32, cert.contents.pCert) if cert and cert.contents.pCert else None
    finally:
        data.dwStateAction = WTD_STATEACTION_CLOSE
        wintrust.WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(data))

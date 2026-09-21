"""Die vier berth-Module sind wortgleiche Kopien aus der berth-allocation-demo (Commit 6f17c3b). Prüfsummen (SHA-256, Zeilenenden normalisiert)
verhindern, dass sie unbemerkt auseinanderlaufen; wer ein Modul bewusst ändert, aktualisiert Prüfsumme und diesen Hinweis."""

import hashlib
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHA256 = {
    "berth_scenario.py": "6b2387b6714657bf23156e5db8c0948615c053294c824030564afd75d7f0284b",
    "berth_heuristic.py": "24badf71bc2354b87220599971b3c5be3d9926fc5fd30382e46c05dc3775f435",
    "berth_evaluation.py": "e77125a2b0ec516fcc24a9631fdb974c9382de5efcba21edaba64e66883c5725",
    "berth_cp_solver.py": "c34f08fb6a5ad75abc4e842f6a4ef56eec9556da754907798b9d0b9b186d7618",
}


@pytest.mark.parametrize("name", SHA256)
def test_copied_berth_module_is_unchanged(name):
    data = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == SHA256[name]

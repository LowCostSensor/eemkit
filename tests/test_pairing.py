import pytest

from eemkit import PairingError, read_pairing

HEADER = "sample_id,eem_file,eem_blank_file,abs_file,abs_blank_file,include,river"


@pytest.fixture
def files(write):
    for f in ("f/S1.csv", "f/S2.csv", "f/Blank.csv", "a/S1.csv", "a/Blank.csv"):
        write(f, "x")
    return write


def test_reads_and_converts_include(files):
    p = files("pairing.csv", "\n".join([
        HEADER,
        "S1,f/S1.csv,f/Blank.csv,a/S1.csv,a/Blank.csv,yes,Merse",
        "S2,f/S2.csv,f/Blank.csv,,,NO,Merse",
        "S3,f/missing.csv,,,,no,Merse",  # excluded rows are not checked
    ]))
    df = read_pairing(p)
    assert list(df["include"]) == [True, False, False]
    assert df.attrs["data_root"] == str(p.parent)
    assert df.loc[1, "abs_file"] == ""


def test_semicolon_separator_and_optional_columns(files):
    p = files("pairing.csv", "sample_id;eem_file;include\r\nS1;f/S1.csv;Sì\r\n", "cp1252")
    df = read_pairing(p)
    assert bool(df.loc[0, "include"])
    assert df.loc[0, "eem_blank_file"] == ""


def test_all_problems_reported_at_once(files):
    p = files("pairing.csv", "\n".join([
        HEADER,
        "S1,f/S1.csv,f/nope.csv,,,yes,x",
        "S1,f/S2.csv,,,,yes,x",
        ",,,,,yes,x",
        "S4,f/S1.csv,,,,maybe,x",
    ]))
    with pytest.raises(PairingError) as err:
        read_pairing(p)
    msg = str(err.value)
    for part in ("nope.csv", "'S1' used by rows 2, 3", "empty sample_id",
                 "eem_file is empty", "'maybe' is not yes/no"):
        assert part in msg


def test_missing_required_column(files):
    p = files("pairing.csv", "sample_id,eem_file\nS1,f/S1.csv\n")
    with pytest.raises(PairingError, match="include"):
        read_pairing(p)


def test_data_root_elsewhere(files, tmp_path):
    p = files("tables/pairing.csv", "sample_id,eem_file,include\nS1,f/S1.csv,yes\n")
    with pytest.raises(PairingError, match="not found"):
        read_pairing(p)
    assert read_pairing(p, data_root=tmp_path).shape[0] == 1

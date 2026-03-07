from app.normalizer import normalize

def test_lowercase():
    assert normalize("POSOSI") == normalize("pososi")

def test_ru_latin_equiv():
    assert normalize("POSOSI") == normalize("Пососи")

def test_strip_feat():
    assert normalize("Track (feat. MORGENSHTERN)") == normalize("Track")

def test_strip_prod():
    assert normalize("Track [prod. Канье]") == normalize("Track")

def test_strip_remix():
    assert normalize("Track (Remix)") == normalize("Track")

def test_strip_artist_prefix():
    assert normalize("3grave - OBEZUMEL") == normalize("OBEZUMEL")

def test_whitespace_normalized():
    assert normalize("  hello   world  ") == normalize("hello world")

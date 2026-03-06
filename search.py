import xmltodict
from index import TrackIndex


def _virtual_to_song_dict(vt: dict) -> dict:
    """Конвертировать виртуальный трек в формат Subsonic song."""
    return {
        "@id": vt["id"],
        "@title": vt["title"],
        "@artist": vt["artist"],
        "@album": vt["album"],
        "@duration": str(vt.get("duration", 0)),
        "@isVirtual": "true",
        "@contentType": "audio/opus",
        "@suffix": "opus",
        "@isDir": "false",
        "@type": "music",
    }


async def augment_search3(
    gonic_xml: str,
    virtual_tracks: list[dict],
    index: TrackIndex,
) -> str:
    """Добавить виртуальные треки в XML ответ search3."""
    data = xmltodict.parse(gonic_xml)
    resp = data["subsonic-response"]
    sr3 = resp.setdefault("searchResult3", {})

    existing_songs = sr3.get("song", [])
    if isinstance(existing_songs, dict):
        existing_songs = [existing_songs]

    # Фильтровать виртуальные треки через индекс по title
    filtered_virtuals = []
    for vt in virtual_tracks:
        is_dup = await index.exists_normalized(vt["title"])
        if not is_dup:
            filtered_virtuals.append(vt)

    all_songs = existing_songs + [_virtual_to_song_dict(vt) for vt in filtered_virtuals]
    sr3["song"] = all_songs

    return xmltodict.unparse(data, pretty=True)

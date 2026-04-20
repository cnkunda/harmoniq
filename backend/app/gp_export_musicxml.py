"""Minimal MusicXML (score-partwise) from Guitar Pro song — structural interchange."""

from __future__ import annotations

import io
import xml.sax.saxutils as xs

import guitarpro as gp


def song_to_musicxml_bytes(song: gp.Song) -> bytes:
    """Return a small valid MusicXML 3.1 document (placeholder notation; metadata from GP file)."""
    title = xs.escape((song.title or "").strip() or "Untitled")
    subtitle = xs.escape((song.subtitle or "").strip())
    composer = xs.escape((song.artist or "").strip())

    sub_block = (
        f'<direction placement="below"><direction-type><words>{subtitle}</words></direction-type></direction>' if subtitle else ""
    )
    comp_block = (
        f'<direction placement="below"><direction-type><words>{composer}</words></direction-type></direction>' if composer else ""
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <movement-title>{title}</movement-title>
  <identification>
    <encoding>
      <software>Harmoniq export</software>
    </encoding>
  </identification>
  <defaults>
    <scaling>
      <millimeters>7</millimeters>
      <tenths>40</tenths>
    </scaling>
  </defaults>
  <part-list>
    <score-part id="P1">
      <part-name>Guitar</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time>
          <beats>4</beats>
          <beat-type>4</beat-type>
        </time>
        <clef>
          <sign>G</sign>
          <line>2</line>
        </clef>
      </attributes>
      <direction placement="above">
        <direction-type>
          <words font-weight="bold">{title}</words>
        </direction-type>
      </direction>
      {sub_block}
      {comp_block}
      <note>
        <rest measure="yes"/>
        <duration>4</duration>
        <voice>1</voice>
      </note>
    </measure>
  </part>
</score-partwise>
"""
    return xml.encode("utf-8")


def gp5_bytes_to_musicxml(gp5_bytes: bytes) -> bytes:
    bio = io.BytesIO(gp5_bytes)
    song = gp.parse(bio)
    return song_to_musicxml_bytes(song)

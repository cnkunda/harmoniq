import music21 as m21
from fractions import Fraction
score = m21.stream.Score()
part = m21.stream.Part()
m = m21.stream.Measure()
ql = float(0.31592)
quantized_ql = Fraction(round(ql * 8), 8)
print(f'Quantized QL: {quantized_ql}')
m.append(m21.note.Note('C4', quarterLength=quantized_ql))
part.append(m)
score.append(part)
try:
    m21.musicxml.m21ToXml.GeneralObjectExporter().parse(score)
    print('Exported WITH Fraction quantization!')
except Exception as e:
    print('Error WITH Fraction quantization:', e)

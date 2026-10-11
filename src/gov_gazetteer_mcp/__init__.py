"""An MCP server over GOV, the Geschichtliches Orts-Verzeichnis.

GOV is the historical gazetteer of the Verein für Computergenealogie
(CompGen): about 1.2 million places, mostly in Germany and the lands that were
German or Prussian, each with its names, types and enclosing places dated. The
server reads GOV's public SOAP web service and answers the questions a
genealogist asks of a village in a given year: what it was called, which Kreis
and province held it, and which parish and Standesamt kept its registers.
Nothing here writes anywhere, and nothing here keeps a family tree.
"""

__version__ = "0.1.0"

#prova que o pacote é importável e que o pytest está configurado. O valor não está no que ele testa, e sim em que, quando um teste real falhar no M2, você já sabe que a ferramenta não é a causa.
def test_pacote_importa():
    import etl  # noqa: F401
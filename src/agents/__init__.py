from .writer      import WriterAgent
from .critic      import CriticAgent
from .editor      import EditorAgent
from .archivist   import ArchivistAgent
from .producer    import ProducerAgent
from .character   import CharacterAgent
from .structure   import StructureAgent
from .logline     import LoglineAgent
from .treatment   import TreatmentAgent
from .lore        import LoreAgent
from .showrunner  import ShowrunnerAgent

AGENT_REGISTRY: dict[str, type] = {
    "writer":      WriterAgent,
    "critic":      CriticAgent,
    "editor":      EditorAgent,
    "archivist":   ArchivistAgent,
    "producer":    ProducerAgent,
    "character":   CharacterAgent,
    "structure":   StructureAgent,
    "logline":     LoglineAgent,
    "treatment":   TreatmentAgent,
    "lore":        LoreAgent,
    "showrunner":  ShowrunnerAgent,
}

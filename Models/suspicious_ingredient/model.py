import torch.nn as nn

INPUT_DIM = 1024
HIDDEN_DIM = 1536
NUM_HEADS = 16
FF_DIM = HIDDEN_DIM * 2
NUM_LAYERS = 12
DROPOUT_RATE = 0.3


class SAB(nn.Module):
    def __init__(self, dim, num_heads, ff_dim, dropout_rate):
        super().__init__()
        self.attn = nn.MultiheadAttention(dim, num_heads, batch_first=True, dropout=dropout_rate)
        self.ff = nn.Sequential(
            nn.Linear(dim, ff_dim),
            nn.GELU(),
            nn.Dropout(dropout_rate),
            nn.Linear(ff_dim, dim),
        )
        self.ln1 = nn.LayerNorm(dim)
        self.ln2 = nn.LayerNorm(dim)

    def forward(self, x, mask=None):
        attn_out, _ = self.attn(x, x, x, key_padding_mask=mask)
        x = self.ln1(x + attn_out)
        return self.ln2(x + self.ff(x))


class SetTransformerForClassification(nn.Module):
    def __init__(self, input_dim=INPUT_DIM, hidden_dim=HIDDEN_DIM, num_heads=NUM_HEADS,
                 ff_dim=FF_DIM, num_layers=NUM_LAYERS, dropout_rate=DROPOUT_RATE):
        super().__init__()
        self.input_proj = nn.Linear(input_dim, hidden_dim)
        self.layers = nn.ModuleList([SAB(hidden_dim, num_heads, ff_dim, dropout_rate) for _ in range(num_layers)])
        self.output_classifier = nn.Linear(hidden_dim, 1)
        self.dropout = nn.Dropout(dropout_rate)

    def forward(self, x, padding_mask):
        h = self.dropout(self.input_proj(x))
        for layer in self.layers:
            h = layer(h, mask=padding_mask)
        return self.output_classifier(h)

# Auto-generated training script (representative of LLM-written research code).
# Not executed in the demo; the agent reads it to explain what the runs did.
import math, argparse
import torch, torch.nn.functional as F
from torch.utils.data import DataLoader
from model import GPT, GPTConfig  # noqa
from data import TokenDataset  # noqa


def get_lr(it, cfg):
    # linear warmup then cosine decay to 0
    if cfg.warmup_steps > 0 and it < cfg.warmup_steps:
        return cfg.lr * it / cfg.warmup_steps
    if it > cfg.max_steps:
        return 0.0
    ratio = (it - cfg.warmup_steps) / max(1, cfg.max_steps - cfg.warmup_steps)
    return cfg.lr * 0.5 * (1.0 + math.cos(math.pi * ratio))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lr", type=float, default=6e-4)
    p.add_argument("--warmup_steps", type=int, default=2000)
    p.add_argument("--max_steps", type=int, default=10000)
    p.add_argument("--batch_size", type=int, default=64)
    p.add_argument("--weight_decay", type=float, default=0.1)
    p.add_argument("--grad_clip", type=float, default=0.0)  # NOTE: 0 disables clipping
    p.add_argument("--run_id", type=str, required=True)
    cfg = p.parse_args()

    model = GPT(GPTConfig(n_layer=12, n_head=12, n_embd=640)).cuda()
    decay = [p_ for n, p_ in model.named_parameters() if p_.dim() >= 2]
    no_decay = [p_ for n, p_ in model.named_parameters() if p_.dim() < 2]
    opt = torch.optim.AdamW(
        [{"params": decay, "weight_decay": cfg.weight_decay}, {"params": no_decay, "weight_decay": 0.0}],
        lr=cfg.lr, betas=(0.9, 0.95), eps=1e-8,
    )
    dl = DataLoader(TokenDataset("train"), batch_size=cfg.batch_size, shuffle=True, drop_last=True)
    val_dl = DataLoader(TokenDataset("val"), batch_size=cfg.batch_size)
    log = open(f"metrics/{cfg.run_id}.csv", "w")
    log.write("step,train_loss,val_loss,grad_norm,lr\n")
    it, data_iter = 0, iter(dl)
    while it <= cfg.max_steps:
        lr = get_lr(it, cfg)
        for g in opt.param_groups:
            g["lr"] = lr
        try:
            x, y = next(data_iter)
        except StopIteration:
            data_iter = iter(dl); x, y = next(data_iter)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits = model(x.cuda())
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), y.cuda().view(-1))
        opt.zero_grad(set_to_none=True)
        loss.backward()
        if cfg.grad_clip > 0:
            gn = torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip)
        else:
            gn = torch.sqrt(sum((p_.grad.detach() ** 2).sum() for p_ in model.parameters() if p_.grad is not None))
        opt.step()
        if it % 100 == 0:
            model.eval(); vl = 0.0
            with torch.no_grad():
                for i, (vx, vy) in enumerate(val_dl):
                    if i >= 20: break
                    vl += F.cross_entropy(model(vx.cuda()).flatten(0, 1), vy.cuda().flatten()).item()
            model.train()
            log.write(f"{it},{loss.item():.4f},{vl/20:.4f},{gn.item():.3f},{lr:.3e}\n"); log.flush()
        it += 1


if __name__ == "__main__":
    main()

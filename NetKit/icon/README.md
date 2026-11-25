# NetKit Icons

**A unified icon collection for network proxy clients.**

适用于 Mihomo、sing-box、Surge、Quantumult X、Loon、Egern 等网络代理客户端。

**[在线浏览和搜索图标](https://kakbga.github.io/NetKit/)**

- 规格为 144 × 144 的透明 PNG。
- [Apps](apps/) 用于应用与服务，[Flags](flags/) 用于地区，[Groups](groups/) 用于策略组。

## Usage · 使用说明

在图标库中点击 **Copy URL**，将 GitHub Raw URL 粘贴到客户端的图标配置中。点击图标可直接打开原始 PNG。文件名区分大小写。

Mihomo 配置示例：

```yaml
proxy-groups:
  - name: Pick
    type: select
    proxies:
      - DIRECT
    icon: https://raw.githubusercontent.com/kakbga/Icon-backup/main/NetKit/icon/groups/Planet.png
```

## Updates · 更新图标

将 PNG 添加到对应的分类目录，或在目录中删除、重命名文件，然后将变更提交并推送到 `main`。GitHub Actions 会重新生成清单并部署图标库。

首次部署时，在仓库 **Settings → Pages → Build and deployment → Source** 中选择 **GitHub Actions**。可在 **Actions** 中运行 **Deploy NetKit to GitHub Pages** 来触发首次部署或重试。

第三方应用名称、品牌标识及商标归其各自权利人所有。项目授权请参阅 [LICENSE](../LICENSE)。

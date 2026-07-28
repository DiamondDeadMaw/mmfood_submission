import "./component_styles.css"

export default function InteractionButton({text, onButtonPress, args=null, color=null, width=null, height=null, 
    fsize=null, fcolor=null}) {
    const buttonStyle = {
        backgroundColor: color || undefined,
        width: width || undefined,
        height: height || undefined,
        fontSize: fsize || undefined,
        color: fcolor || undefined
    };
    return (
        <div className="interaction-button" onClick={() => (args !== null ? onButtonPress(...args) : onButtonPress())} 
        style={buttonStyle}
        >
            {text}
        </div>
    )
}
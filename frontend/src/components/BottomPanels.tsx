import { Panel1 } from './Panel1';
import { Panel2 } from './Panel2';
import { Panel3 } from './Panel3';

interface BottomPanelsProps {
  feed: any[];
  govActions: any[];
  protests: any[];
  scoresArr: [string, number][];
  chokepoints: any[];
  topAggression: any[];
  cascade: any[];
  topRoutes: any[];
  predictions: any[];
  headlines: any[];
  commodities: any[];
  freight: any[];
  flights: any[];
  quakesNear: any[];
}

export function BottomPanels(props: BottomPanelsProps) {
  return (
    <div className="bottom-row">
      <Panel1
        feed={props.feed}
        govActions={props.govActions}
        protests={props.protests}
      />
      <Panel2
        scoresArr={props.scoresArr}
        chokepoints={props.chokepoints}
        aggression={props.topAggression}
        cascade={props.cascade}
        routes={props.topRoutes}
      />
      <Panel3
        predictions={props.predictions}
        headlines={props.headlines}
        commodities={props.commodities}
        freight={props.freight}
        flights={props.flights}
        quakesNear={props.quakesNear}
      />
    </div>
  );
}